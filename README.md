# A股 + 加密货币 盯盘推送

两套独立推送系统：
- **A股盯盘**：交易时段每半小时，七方联席实时研判（3 交易员 + 4 研究员 + 1 分析师 + 持仓建议）
- **加密盯盘**：每天早中晚各一次（07:00/12:00/18:00），BTC+ETH 关键位置标注（支撑/阻力/均线/指标/操作建议）

均通过 QQ 邮箱推送（关 App 也能收到）。

## 工作原理

```
外部定时器 (cron-job.org 等，每30分钟)
    ↓ 触发 GitHub Actions workflow_dispatch
GitHub Actions 运行 monitor.py
    ↓ 抓取东方财富行情 + 生成七方研判
双通道推送：
    ├─ 飞书自定义机器人 → 飞书群（手机通知栏直推）📱
    └─ QQ 邮箱 SMTP    → 微信/邮箱通知（兜底）
```

> ⚠️ **关于定时**：GitHub Actions 自带的 `schedule` 在免费版/新仓库上经常被吞（实测历史记录里零条 schedule 触发）。因此**自动点火依赖外部定时器** `trigger.sh`（部署到 cron-job.org 等），由它调用 GitHub 接口触发本工作流。飞书/邮件只是送达渠道，不负责定时。

## 飞书机器人配置（必做）

1. 飞书群 → 设置 → 群机器人 → 添加机器人 → 选「自定义机器人」
2. 复制 Webhook 地址（形如 `https://open.feishu.cn/open-apis/bot/v2/hook/xxxx`）
3. 加到仓库 Secrets：`Settings → Secrets → Actions → New → 名称 FEISHU_WEBHOOK`，值填 Webhook 地址
4. （可选）仅用飞书、停发邮件：新增 Secret `FEISHU_ONLY=true`

## 外部定时器配置（自动每半小时推送必做）

> **当前选定方案：小米手机 Termux + curl**（开源、token 仅存本机，详见 `termux-trigger/setup.md`）。
> 手机装开源 Termux，crond 每30分钟 POST 调 GitHub dispatch，关对话 App 也能推。
> 备选：MacroDroid 自动化（`phone-trigger-guide.md`）、cron-job.org 云端定时（最稳）、联想 T2 NAS 跑 Docker 容器（`nas-trigger/`）。

部署要点（详见 `termux-trigger/setup.md`）：
1. F-Droid 装 **Termux**（+ 可选 **Termux:Boot** 开机自启）
2. `pkg install curl cronie termux-services tzdata`
3. token 写入 `~/.github_token`（chmod 600，细粒度单仓 Actions 权限）
4. `sv-enable crond && sv up crond`；crontab 加 `*/30 1-7 * * 1-5 $HOME/trigger.sh`
5. MIUI 给 Termux 设「电池无限制 + 自启动」防杀后台

## 标的池（仅沪深主板/ETF/可转债，不含创业板/科创板）

- 通富微电 (002156) - 深市主板
- 长电科技 (600584) - 沪市主板
- 中国石油 (601857) - 沪市主板
- 通信ETF华夏 (515050) - 沪市ETF（AI算力通信主线）
- 创业板50ETF (159949) - 用户持仓

## 七方阵容

- 交易员：炒股养家（情绪周期）、花荣（盲点套利）、赵老哥（龙头战法）
- 研究员：张忆东（全球视野）、荀玉根（策略配置）、高善文（市场水位）、付鹏（全球宏观）
- 分析师：老艾（散户视角）

## 注意事项

- 数据来源东方财富公开接口，有 3–5 分钟延迟
- 仅交易日（周一至周五）推送
- 模拟仓位每人均 3 万元，从首次运行时点起算，记录于 `portfolio_state.json`

## 加密货币盯盘（crypto_monitor.py）

每天早中晚各一次推送 BTC+ETH 关键位置标注。

**推送时间**（北京时间）：07:00 早盘 | 12:00 午盘 | 18:00 晚盘

**工作原理**：
```
GitHub Actions 定时触发（每天3次）
    ↓
crypto_monitor.py 从 Binance 抓 K线数据
    ↓
自己计算 SMA/EMA/RSI/Stoch/布林带 等技术指标
    ↓
标注支撑/阻力/趋势/操作建议
    ↓
QQ 邮箱推送 📱
```

**标注内容**：
- 阻力位：SMA200/100/50/20、30天高点、布林上轨
- 支撑位：SMA20/50、7天低点、30天低点、布林下轨
- 指标：RSI(14)、Stochastic %K、超买超卖状态
- 趋势：价在 SMA50/200 上方/下方 → 多空判断
- 操作：近阻力/近支撑的具体应对策略

**数据源**：Binance K线 API（公开免 key，GitHub Actions 美国机房可访问）
