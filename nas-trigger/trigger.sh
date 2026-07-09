#!/bin/bash
# T2 Docker 容器内运行：每30分钟（仅交易时段）调 GitHub dispatch 点火
# 依赖：curl；环境变量 GITHUB_TOKEN / REPO / WORKFLOW
set -euo pipefail

REPO="${REPO:-holgeraaa/stock-monitor}"
WORKFLOW="${WORKFLOW:-monitor.yml}"
TOKEN="${GITHUB_TOKEN:?缺少环境变量 GITHUB_TOKEN}"

# 北京时间交易时段判断（容器已设 TZ=Asia/Shanghai，date 直接出北京时）
H=$(date +%H); M=$(date +%M); D=$(date +%u)
TRADING=false
if [ "$D" -le 5 ]; then
  if { [ "$H" -eq 9 ] && [ "$M" -ge 30 ]; } || [ "$H" -eq 10 ] \
     || { [ "$H" -eq 11 ] && [ "$M" -le 30 ]; } || [ "$H" -eq 13 ] || [ "$H" -eq 14 ]; then
    TRADING=true
  fi
fi

if $TRADING; then
  CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 10 -X POST \
    -H "Authorization: token $TOKEN" \
    -H "Accept: application/vnd.github+json" \
    "https://api.github.com/repos/$REPO/actions/workflows/$WORKFLOW/dispatches" \
    -d '{"ref":"main"}')
  echo "$(date '+%F %T') [点火] dispatch -> HTTP $CODE"
else
  echo "$(date '+%F %T') [跳过] 非交易时段"
fi
