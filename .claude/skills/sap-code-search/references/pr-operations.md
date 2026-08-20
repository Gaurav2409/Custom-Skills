# PR & Repo Operations on SAP GitHub

## PR Commands

Use `--repo github.wdf.sap.corp/OWNER/REPO` (the `-R` flag) to target SAP repos:

```bash
# List PRs (default: open)
gh pr list --repo github.wdf.sap.corp/bizx/au-servicecenter

# List all PRs (open, closed, merged)
gh pr list --repo github.wdf.sap.corp/bizx/au-servicecenter --state all

# View a specific PR
gh pr view 87 --repo github.wdf.sap.corp/bizx/au-servicecenter

# View PR diff
gh pr diff 87 --repo github.wdf.sap.corp/bizx/au-servicecenter

# View PR comments
gh pr view 87 --repo github.wdf.sap.corp/bizx/au-servicecenter --comments

# View PR as JSON
gh pr view 87 --repo github.wdf.sap.corp/bizx/au-servicecenter --json title,body,files
```

## Fetch File Contents

Only fetch individual files when the full content is needed (not just a matched fragment):

```bash
# Fetch and decode file content
GH_HOST=github.wdf.sap.corp gh api /repos/OWNER/REPO/contents/path/to/file \
  --jq '.content' | base64 -d

# List directory contents
GH_HOST=github.wdf.sap.corp gh api /repos/OWNER/REPO/contents/src/main/java \
  --jq '.[].name'
```

## Repo Info

```bash
# Get default branch
GH_HOST=github.wdf.sap.corp gh api /repos/bizx/au-servicecenter --jq '.default_branch'
```

**When filtering fetched content, always use `python3` or basic `grep -E` (no `grep -P` on macOS).**
