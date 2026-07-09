# A股盯盘推送

交易时段每半小时自动抓取 A 股行情，生成"七方联席实时研判"（3 交易员 + 4 研究员 + 1 分析师 + 你的持仓建议），通过 **飞书群机器人 + QQ 邮箱** 双通道推送。

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

> **当前选定方案：小米手机 MacroDroid 自动化**（详见 `phone-trigger-guide.md`）。
> 手机装 MacroDroid，定时 POST 调 GitHub dispatch 即可，关对话 App 也能推。
> 备选：cron-job.org 云端定时（最稳）、或联想 T2 NAS 跑 Docker 容器（`nas-trigger/`）。

1. 打开 https://cron-job.org 注册，新建 job（最省心、最可靠的云端方案）
2. URL 填一个能触发本仓库 workflow 的中转地址（见下），或在本机 crontab 里跑 `trigger.sh`
3. 频率：每 30 分钟；时间窗口：周一至周五 09:30–11:30 / 13:00–15:00（脚本内部也会再判一次交易时段）

`trigger.sh` 需设置环境变量 `GITHUB_TOKEN`（有 workflow 权限的 token）。

## 标的池（仅沪深主板/ETF/可转债，不含创业板/科创板）

- 通富微电 (002156) - 深市主板
- 长电科技 (600584) - 沪市主板
- 中国石油 (601857) - 沪市主板
- 创业板50ETF (159949) - 用户持仓

## 七方阵容

- 交易员：炒股养家（情绪周期）、花荣（盲点套利）、赵老哥（龙头战法）
- 研究员：张忆东（全球视野）、荀玉根（策略配置）、高善文（市场水位）、付鹏（全球宏观）
- 分析师：老艾（散户视角）

## 注意事项

- 数据来源东方财富公开接口，有 3–5 分钟延迟
- 仅交易日（周一至周五）推送
- 模拟仓位每人均 3 万元，从首次运行时点起算，记录于 `portfolio_state.json`
