#!/bin/bash
# Termux（小米平板）内运行：直接跑 monitor.py 完整流水线
# 抓行情 + 生成七方报告 + 发邮件，全程不经 GitHub
cd "$HOME/stock-monitor" || { echo "$(date '+%F %T') [错误] 找不到 ~/stock-monitor"; exit 1; }
echo "$(date '+%F %T') [启动] monitor.py"
python monitor.py >> "$HOME/stock-monitor/run.log" 2>&1
echo "$(date '+%F %T') [结束] exit=$?"
