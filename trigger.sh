#!/bin/bash
# 外部 cron 触发器
# 部署到 cron-job.org 等外部定时服务
# 自动判断交易时段，是则触发 GitHub Actions

REPO="holgeraaa/stock-monitor"
WORKFLOW="monitor.yml"

# 判断交易时段 (北京时间)
HOUR=$(TZ='Asia/Shanghai' date +%H)
MINUTE=$(TZ='Asia/Shanghai' date +%M)
WEEKDAY=$(TZ='Asia/Shanghai' date +%u)

IS_TRADING=false
if [ "$WEEKDAY" -le 5 ]; then
    if [ "$HOUR" -eq 9 ] && [ "$MINUTE" -ge 30 ]; then IS_TRADING=true; fi
    if [ "$HOUR" -eq 10 ]; then IS_TRADING=true; fi
    if [ "$HOUR" -eq 11 ] && [ "$MINUTE" -le 30 ]; then IS_TRADING=true; fi
    if [ "$HOUR" -eq 13 ] || [ "$HOUR" -eq 14 ]; then IS_TRADING=true; fi
fi

if [ "$IS_TRADING" = true ]; then
    echo "[$(date)] 交易时段，触发 GitHub Actions..."
    RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
      -H "Authorization: token ${GITHUB_TOKEN}" \
      -H "Accept: application/vnd.github+json" \
      "https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches" \
      -d '{"ref":"main"}')
    echo "HTTP Status: ${RESPONSE}"
else
    echo "[$(date)] 非交易时段，跳过。"
fi
