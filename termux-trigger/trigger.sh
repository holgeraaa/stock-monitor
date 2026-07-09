#!/bin/bash
# Termux（小米手机）内运行：每30分钟（仅交易时段）调 GitHub dispatch 点火
# token 从 ~/.github_token 读取（chmod 600），不写死在脚本里
# 依赖：curl、tzdata（TZ=Asia/Shanghai 才认）、crond（由 termux-services 管理）

TOKEN_FILE="$HOME/.github_token"
TOKEN=$(cat "$TOKEN_FILE" 2>/dev/null)
if [ -z "$TOKEN" ]; then
  echo "$(date '+%F %T') [错误] 找不到 $TOKEN_FILE"
  exit 1
fi

REPO="holgeraaa/stock-monitor"
WORKFLOW="monitor.yml"

# 北京时间交易时段判断（手机已装 tzdata，date 才认 Asia/Shanghai）
H=$(TZ=Asia/Shanghai date +%H); M=$(TZ=Asia/Shanghai date +%M); D=$(TZ=Asia/Shanghai date +%u)
TRADING=false
if [ "$D" -le 5 ]; then
  if { [ "$H" = 9 ] && [ "$M" -ge 30 ]; } || [ "$H" = 10 ] \
     || { [ "$H" = 11 ] && [ "$M" -le 30 ]; } || [ "$H" = 13 ] || [ "$H" = 14 ]; then
    TRADING=true
  fi
fi

if $TRADING; then
  CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 10 -X POST \
    -H "Authorization: token $TOKEN" \
    -H "Accept: application/vnd.github+json" \
    "https://api.github.com/repos/$REPO/actions/workflows/$WORKFLOW/dispatches" \
    -d '{"ref":"main"}')
  echo "$(TZ=Asia/Shanghai date '+%F %T') [点火] dispatch -> HTTP $CODE"
else
  echo "$(TZ=Asia/Shanghai date '+%F %T') [跳过] 非交易时段"
fi
