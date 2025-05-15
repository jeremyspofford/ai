import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import gitlab
import hcl2
import openai

# ——— Helpers ———


def run_tfsec(src, out):
    result = subprocess.run([
        "tfsec", src,
        "--format", "json",
        "--out", out
    ], check=False)
    if result.returncode != 0:
        print(
            f"tfsec exited with code {result.returncode}. This usually means issues were found.")


def parse_hcl(src_dir):
    regs = []
    for tf in Path(src_dir).rglob("*.tf"):
        try:
            with open(tf, "r") as f:
                regs.append(hcl2.load(f))
        except Exception as e:
            print(f"Warning: Failed to parse {tf}: {e}")
    return regs


def prompt_llm(findings, hcl_ast):
    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    prompt = f"""
You are a security auditor. Given these static-scan findings:
{json.dumps(findings, indent=2)}

And this Terraform AST excerpt:
{json.dumps(hcl_ast, indent=2)}

Suggest:
1) What's risky?
2) How to fix it? (Terraform snippet)
Output JSON: {{ "issues": [{{ "risk": ..., "recommendation": ... }}] }}
"""
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
    )
    content = resp.choices[0].message.content
    if not content or not content.strip():
        print("ERROR: OpenAI returned an empty response. Raw response below:")
        print(repr(content))
        raise RuntimeError("OpenAI returned empty response.")

    # Extract JSON code block if present
    match = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", content)
    if match:
        json_str = match.group(1)
    else:
        # fallback: try to find any {...} block
        match = re.search(r"(\{[\s\S]*\})", content)
        if match:
            json_str = match.group(1)
        else:
            print("ERROR: Could not find JSON in OpenAI response. Raw response below:")
            print(content)
            raise RuntimeError("No JSON found in OpenAI response.")

    try:
        return json.loads(json_str)
    except Exception as e:
        print("ERROR: OpenAI did not return valid JSON. Extracted string below:")
        print(json_str)
        raise


def create_mr(project_id, branch_name, report_path):
    gl = gitlab.Gitlab(os.getenv("CI_SERVER_URL"),
                       private_token=os.getenv("GITLAB_TOKEN"))
    proj = gl.projects.get(project_id)
    # Create a fix branch
    proj.branches.create({"branch": branch_name, "ref": proj.default_branch})
    # Commit the report or recommended fixes (omitted for brevity)
    # ...
    # Open MR
    mr = proj.mergerequests.create({
        "source_branch": branch_name,
        "target_branch": proj.default_branch,
        "title": "[AI Audit] Security fixes",
        "description": Path(report_path).read_text(),
    })
    return mr.web_url

# ——— Main Flow ———


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--source-dir", required=True)
    p.add_argument("--tfsec-out", required=True)
    p.add_argument("--report-out", required=True)
    args = p.parse_args()

    # 1. Run tfsec
    run_tfsec(args.source_dir, args.tfsec_out)
    findings = json.load(open(args.tfsec_out))

    # 2. Parse HCL for context
    hcl_ast = parse_hcl(args.source_dir)

    # 3. Call LLM for human-readable suggestions
    ai_report = prompt_llm(findings, hcl_ast)

    # 4. Write audit_report.md
    with open(args.report_out, "w") as f:
        f.write("# AI Security Audit Report\n\n")
        for issue in ai_report["issues"]:
            f.write(f"## Risk: {issue['risk']}\n")
            f.write(f"{issue['recommendation']}\n\n")

    # 5. If critical issues, open a MR with fixes
    if any("critical" in i["risk"].lower() for i in ai_report["issues"]):
        mr_url = create_mr(
            project_id=int(os.getenv("CI_PROJECT_ID")),
            branch_name=f"ai-fixes/{os.getenv('CI_COMMIT_SHORT_SHA')}",
            report_path=args.report_out,
        )
        print(f"🔗 Merge Request opened: {mr_url}")
