# 小米平板 Termux 完整自托管指南（直接跑 monitor.py，不经 GitHub）

> 平板上装开源 Termux，crond 每30分钟直接跑 `monitor.py` 完整流水线
> （抓行情 + 七方报告 + 发邮件）。GitHub 完全不参与。
> 本质 = 一台"迷你自托管服务器"，与笔记本自托管等价，但底层是 Android，稳定性弱于笔记本的 systemd。

## 第零步：拿代码（其实已有，邮箱凭证在脚本里）

`monitor.py` 里的 QQ 邮箱 + 授权码是硬编码的（和你之前收到邮件时一致），**无需额外 token**。
飞书可选（不设 `FEISHU_WEBHOOK` 环境变量就只用邮件）。

## 第一步：装 Termux（F-Droid 版）

- 从 **F-Droid** 搜 **Termux** 安装（⚠️ 别用 Google Play 版，已停更受限）
- 可选装 **Termux:Boot**（开机自启 crond）

## 第二步：在 Termux 里装依赖 + 拉代码

```bash
pkg update -y
pkg install -y python git termux-services
pip install requests        # monitor.py 唯一外部依赖（纯Python，无需编译）
```
> 若 `pip` 不存在先 `pkg install python-pip`；Termux 的 pip 装 requests 不需要 clang。

```bash
git clone https://github.com/holgeraaa/stock-monitor.git ~/stock-monitor
chmod +x ~/stock-monitor/termux-selfhost/run.sh
```

## 第三步：启 crond 并设开机自启

```bash
sv-enable crond
sv up crond
```

## 第四步：加 crontab（每30分钟；脚本内部自判交易时段，非交易时段自动跳过）

```bash
(crontab -l 2>/dev/null; echo '*/30 * * * * $HOME/termux-selfhost/run.sh') | crontab -
```

> 比起只在交易时段跑，这里简单地"每30分钟都跑一次"，由 monitor.py 自己决定是否发邮件，最稳不出错。

## 第五步：防 MIUI/HyperOS 杀后台（最关键，否则到点不跑）

- 平板 **设置 → 应用设置 → 应用管理 → Termux → 电池 → 无限制**
- 同路径 → **自启动 → 允许**
- 若装了 **Termux:Boot**，同样「无限制 + 自启动」
- Termux 内保持一个会话常驻（或靠 termux-services 后台 daemon），系统才不会回收

## 第六步：验证

```bash
~/termux-selfhost/run.sh          # 交易时段应发邮件；非交易时段打印“非交易时段，跳过”
tail -f ~/stock-monitor/run.log   # 看历史运行记录
```

- 交易时段跑一次 → 约 1 分钟手机收邮件即成功。
- 想立刻测：直接多跑几次 `run.sh` 看邮件是否到达（非交易时段会被脚本跳过，属正常）。

## 维护

- **更新代码**：`cd ~/stock-monitor && git pull`
- **模拟仓位/持仓状态**：`~/stock-monitor/portfolio_state.json`，脚本自维护；要重置删掉它即可
- **日志**：`cat ~/stock-monitor/run.log`

## 安全小结

- Termux 开源，脚本逐行可见；邮箱凭证只在你这台平板 + 仓库里，不进任何第三方服务。
- 比 cron-job.org 等云端定时更私密，比手机自动化更"独立"（直接出邮件，不经 GitHub）。

## 与笔记本自托管的定位

- **笔记本（Debian+systemd）**：主力服务器，开机自启、后台最稳。
- **平板（Termux）**：等价备用服务器；Android 后台限制使其 24h 可靠性略逊于笔记本。
- 两者都跑完整流水线 = 双保险。手机 Termux 触发器、GitHub 手动 dispatch 仍可当更外层的兜底。
