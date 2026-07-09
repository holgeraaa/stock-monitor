# 废弃笔记本 → 24h 自托管服务器（整机自托管，彻底不依赖 GitHub）

> 笔记本自己抓行情 + 生成七方报告 + 发邮件，GitHub 完全出局。
> `monitor.py` 已自包含，本方案零改代码，只靠 systemd 定时跑它。

## 第零步：装系统（推荐 Debian 12 最小安装）

1. 下载 **Debian 12 netinst** 或 **Ubuntu Server 24.04 LTS**，做成 U 盘启动盘（Ventoy/Rufus）。
2. 安装时：
   - 选**最小安装 / 仅 SSH 服务器**（不要桌面环境，省资源、更稳）。
   - 设好用户名 + 密码，记住用户名（下面脚本用它）。
   - 装完能 `ssh 用户名@笔记本IP` 登录即可（建议路由器给笔记本绑个固定 IP，方便 SSH）。
3. 首次登录后换源 + 更新（Debian 示例）：
   ```bash
   sudo apt update && sudo apt upgrade -y
   sudo apt install -y curl git
   ```

> 老笔记本资源有限，**千万别装桌面环境**，纯命令行当无头服务器最省心。

## 第一步：一键部署

把本目录（`laptop-selfhost/`）传到笔记本，例如 `scp -r laptop-selfhost 用户名@笔记本IP:~/`，然后：

```bash
ssh 用户名@笔记本IP
cd ~/laptop-selfhost
chmod +x install.sh
./install.sh
```

脚本会自动：装 Python/requests → 拉代码到 `/opt/stock-monitor` → 建 `stockbot` 用户 → 装 systemd 单元 → **禁用休眠/合盖睡眠**。

## 第二步：验证

```bash
# 手动跑一次（交易时段应发邮件；非交易时段打印“非交易时段，跳过”）
sudo systemctl start stock-monitor.service

# 看日志
journalctl -u stock-monitor.service -n 50

# 看定时器状态
systemctl list-timers stock-monitor.timer
```

- 交易时段跑一次 → 约 1 分钟手机收邮件，即成功。
- 非交易时段跑 → 日志显示跳过，正常。

## 第三步：确认“永不开睡”

`install.sh` 已处理，但装完复核一下：

```bash
cat /etc/systemd/logind.conf.d/99-nosleep.conf   # 应见 HandleLidSwitch=ignore
systemctl is-enabled sleep.target                 # 应显示 masked
```

合盖、插电、常开即可。老笔记本 24h 功耗约 15–40W，当服务器完全够用。

## 维护

- **更新代码**：`cd /opt/stock-monitor && sudo -u stockbot git pull`
- **会员持仓 / 模拟仓位**：状态在 `/opt/stock-monitor/portfolio_state.json`，由脚本自己维护；要重置就删掉它让脚本重建。
- **日志**：`journalctl -u stock-monitor.service`
- **停/启**：`sudo systemctl stop/start stock-monitor.timer`

## 兜底（笔记本关机/断网时）

- **手机 Termux**（见 `../termux-trigger/setup.md`）仍在，可补触发。
- **GitHub 手动 dispatch**：仓库 Actions 页点 Run workflow 也能发（当纯手动兜底）。

## 安全小结

- 全程本机运行，token/邮箱凭证只在你这台笔记本上，不进任何第三方。
- `stockbot` 是无登录权限的专用系统用户，最小权限跑脚本。
- 比 cron-job.org 等云端定时更私密，比手机自动化更稳（不会被电池优化杀）。
