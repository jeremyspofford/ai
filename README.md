# AI Auto-Fix for tfsec Findings in Terraform

![AI Security Bot](AI%20Security%20Bot.png)

This tool leverages OpenAI to automatically suggest and apply fixes to Terraform files flagged by [tfsec](https://github.com/aquasecurity/tfsec) security scans.

## What It Does

- Parses `tfsec_results.json` (output from tfsec) to find all `.tf` files and their associated security issues.
- For each file, prompts OpenAI with the file content and the list of issues, requesting a fixed version of the file (no markdown, just HCL).
- If the AI returns a fix, overwrites the original `.tf` file with the suggested changes.
- Prints a summary of all files changed and suggests a `git add` command for easy staging.
- **Does not** create branches, commits, or merge requests automatically—review and commit changes manually.

## Requirements

- Python 3.8+
- [openai](https://pypi.org/project/openai/) Python package
- [gitlab](https://pypi.org/project/python-gitlab/) Python package (optional, for MR logic if re-enabled)
- An OpenAI API key (`OPENAI_API_KEY` environment variable)
- A `tfsec_results.json` file (from running tfsec)

## Setup

1. Install dependencies:

   ```sh
   pip install openai python-gitlab
   ```

2. Set your OpenAI API key:

   ```sh
   export OPENAI_API_KEY=sk-...your-key...
   ```

3. (Optional) Set up your Python virtual environment as needed.

## Usage

1. Run tfsec on your Terraform codebase:

   ```sh
   tfsec ../infrastructure --format json --out tfsec_results.json
   ```

2. Run the AI auto-fix script from the `scripts/` directory:

   ```sh
   python ai_auto_fix_tfsec.py
   ```

3. Review the output. The script will:
   - Attempt to fix every `.tf` file referenced in `tfsec_results.json` (even if not tracked by git).
   - Overwrite the file with the AI's suggestion if a fix is generated.
   - Print a summary of changed files and a suggested `git add` command.

4. Review, stage, and commit the changes as desired:

   ```sh
   git add <changed-files>
   git commit -m "AI: tfsec auto-fixes"
   git push
   ```

## Workflow

- The script does **not** create a new branch or open a merge request automatically.
- All changes are made in-place to the referenced `.tf` files.
- If a file does not exist, a warning is printed and it is skipped.
- If the AI returns no change, the script prints the original and AI output for debugging.

## Notes

- Always review AI-generated changes before committing.
- The script instructs the AI to return only valid HCL (no markdown code blocks).
- For best results, run the script from the root or `scripts/` directory of your repo.
- You can further customize the prompt or add dry-run/review modes as needed.

---

**Author:** AI-generated, customized for your workflow.
