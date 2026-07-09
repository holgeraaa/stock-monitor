#!/bin/bash
# 笔记本自托管一键部署（Debian/Ubuntu，需以有 sudo 的普通用户运行）
set -e

echo "== 1. 安装依赖 =="
sudo apt update
sudo apt install -y python3 python3-requests git

echo "== 2. 拉取代码到 /opt/stock-monitor =="
sudo mkdir -p /opt/stock-monitor
sudo chown "$USER":"$USER" /opt/stock-monitor
if [ ! -d /opt/stock-monitor/.git ]; then
  git clone --depth 1 https://github.com/holgeraaa/stock-monitor.git /opt/stock-monitor
fi

echo "== 3. 建专用用户 stockbot =="
if ! id stockbot >/dev/null 2>&1; then
  sudo useradd -r -s /usr/sbin/nologin stockbot
fi
sudo chown -R stockbot:stockbot /opt/stock-monitor

echo "== 4. 安装 systemd 单元 =="
SRC="$(cd "$(dirname "$0")" && pwd)"
sudo cp "$SRC/stock-monitor.service" /etc/systemd/system/
sudo cp "$SRC/stock-monitor.timer"   /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now stock-monitor.timer

echo "== 5. 禁用休眠 / 合盖睡眠（24h 服务器必需）=="
sudo mkdir -p /etc/systemd/logind.conf.d
sudo tee /etc/systemd/logind.conf.d/99-nosleep.conf >/dev/null <<'EOF'
[Login]
HandleLidSwitch=ignore
HandleLidSwitchDocked=ignore
IdleAction=ignore
EOF
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
sudo systemctl restart systemd-logind

echo ""
echo "✅ 部署完成。"
echo "查看定时任务： systemctl list-timers stock-monitor.timer"
echo "手动跑一次：   sudo systemctl start stock-monitor.service"
echo "实时看日志：   journalctl -u stock-monitor.service -f"
