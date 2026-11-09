#!/usr/bin/env bash
# Commit this run's data and README changes to the branch, safely.
# Writes changed=true|false to $GITHUB_OUTPUT. Never leaves conflict markers or a half-finished rebase behind.
set -euo pipefail
branch="${GITHUB_REF_NAME:-main}"
out="${GITHUB_OUTPUT:-/dev/null}"

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git add -A README.md data   # data/cache is ignored by .gitignore

if git diff --cached --quiet; then
  echo "changed=false" >> "$out"
  echo "no changes"
  exit 0
fi

git commit -q -m "data: update $(date -u +%Y-%m-%d)"

if git pull --rebase origin "$branch"; then
  git push origin "HEAD:$branch"
  echo "changed=true" >> "$out"
else
  # The same files changed on the branch while this run was working. Keep the branch exactly as it is and let the
  # next run redo this work, instead of publishing a half-merged file.
  git rebase --abort 2>/dev/null || true
  git reset -q --hard "origin/$branch"
  echo "::warning::data changed on $branch during this run; this run's data was dropped and the next run will redo it"
  echo "changed=false" >> "$out"
fi
