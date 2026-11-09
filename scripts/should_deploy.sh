#!/usr/bin/env bash
# Decide whether to publish. Usage: should_deploy.sh <mode> <changed>   (mode: run|retry|none, changed: true|false)
# Daily and push runs always publish. A frequent (retry) run publishes when it changed data, or when the live site is not
# built from the current commit (a failed deploy would otherwise stay stale). No model calls are involved.
# The live build stamp comes from $QTD_LIVE_STAMP (tests) or ${QTD_SITE_URL}/build.txt. An unreadable stamp counts as stale.
set -euo pipefail
mode="${1:?mode}"; changed="${2:?changed}"
out="${GITHUB_OUTPUT:-/dev/null}"
head="$(git rev-parse HEAD)"
deploy=false
if [ "$mode" != "retry" ] || [ "$changed" = "true" ]; then
  deploy=true
else
  live="${QTD_LIVE_STAMP-}"
  if [ -z "${QTD_LIVE_STAMP+x}" ] && [ -n "${QTD_SITE_URL:-}" ]; then
    live="$(curl -fsS --max-time 20 "${QTD_SITE_URL%/}/build.txt" 2>/dev/null | tr -d '[:space:]' || true)"
  fi
  [ "$live" = "$head" ] || deploy=true
fi
echo "deploy=$deploy" >> "$out"
echo "deploy=$deploy (mode=$mode changed=$changed head=${head:0:7})"
