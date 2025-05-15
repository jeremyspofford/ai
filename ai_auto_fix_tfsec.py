import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import gitlab
import openai

# --- Config ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
# TODO: NOT YET IMPLEMENTED
# GITLAB_TOKEN = os.getenv("GITLAB_TOKEN")
# CI_SERVER_URL = os.getenv("CI_SERVER_URL", "https://gitlab.com")
# PROJECT_ID = os.getenv("CI_PROJECT_ID")
# DEFAULT_BRANCH = os.getenv("CI_DEFAULT_BRANCH", "main")
# AUDIT_BRANCH_PREFIX = "ai-tfsec-fixes"
TFSEC_RESULTS = "tfsec_results.json"

# --- Helper: Parse tfsec results ---


def parse_tfsec_results(tfsec_path):
    with open(tfsec_path) as f:
        results = json.load(f)["results"]
    issues_by_file = {}
    for result in results:
        file = result["location"]["filename"]
        if file not in issues_by_file:
            issues_by_file[file] = []
        issues_by_file[file].append(result)
    return issues_by_file

# --- Helper: AI fix for a file ---


def ai_fix_file(file_path, issues):
    with open(file_path) as f:
        file_content = f.read()
    prompt = f"""
You are a Terraform security expert. Here is a Terraform file with security issues found by tfsec:

--- FILE START ---
{file_content}
--- FILE END ---

The following issues were found:
"""
    for issue in issues:
        prompt += f"\n- Resource: {issue['resource']}\n  Risk: {issue['description']}\n  Recommendation: {issue['resolution']}\n"
    prompt += """

Please return ONLY the fixed version of the file, with all issues addressed. Do not include explanations, and do NOT wrap the result in any markdown code block (no ```hcl or ```terraform). Just output the corrected file content as plain text.
"""
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
    )
    content = resp.choices[0].message.content.strip()
    # Remove any code block if present (just in case)
    if content.startswith("```"):
        content = re.sub(r"^```[a-zA-Z]*\\s*|```$", "",
                         content, flags=re.MULTILINE).strip()
    # Only return if the fix is different
    if content and content.strip() != file_content.strip():
        return content
    return None

# --- Helper: Write fixes in-place ---


def write_fixes_in_place(files_to_fixes):
    changed = []
    for file_path, fixed_content in files_to_fixes.items():
        if not os.path.isfile(file_path):
            print(f"  ⚠️ Skipping non-local or missing file: {file_path}")
            continue
        with open(file_path, "w") as f:
            f.write(fixed_content)
        print(f"  ✏️ Wrote AI fix to {file_path}")
        changed.append(file_path)
    return changed

# --- Main ---


def main():
    issues_by_file = parse_tfsec_results(TFSEC_RESULTS)
    files_to_fixes = {}
    for file_path, issues in issues_by_file.items():
        print(f"\nAI fixing: {file_path} ({len(issues)} issues)")
        try:
            fixed = ai_fix_file(file_path, issues)
        except FileNotFoundError:
            print(f"  ⚠️ File not found: {file_path}")
            continue
        if fixed:
            files_to_fixes[file_path] = fixed
            print(f"  ✔️ AI fix generated.")
        else:
            print(f"  ❌ No fix or no change suggested. (AI output below)")
            try:
                with open(file_path) as f:
                    original = f.read()
                print("--- Original file ---")
                print(original)
            except Exception as e:
                print(f"Could not read original file: {e}")
            print("--- AI output ---")
            print(fixed)
    if not files_to_fixes:
        print("No files to fix. Exiting.")
        return
    changed_files = write_fixes_in_place(files_to_fixes)
    if changed_files:
        print("\nReview the changes above, then commit and push them as desired.")
        print("Changed files:")
        for f in changed_files:
            print(f"  {f}")
        print("\nTo stage all changes, run:\n  git add " + " ".join(changed_files))
    else:
        print("No files changed.")


if __name__ == "__main__":
    main()
