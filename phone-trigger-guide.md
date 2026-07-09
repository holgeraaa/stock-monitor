# 小米手机触发器（MacroDroid）部署指南

> 手机只负责"每30分钟调一次 GitHub"，真正的抓行情+发邮件由 GitHub 上的 monitor.py 完成。
> 关掉我们的对话 App 也能推——只要你手机开机在线。

## 第零步：拿一个 scoped GitHub Token（只需一次）

1. GitHub → 右上角头像 → **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**
2. Token name：`stock-monitor-phone`
3. Expiration：建议 90 天（到期重新生成即可）
4. Repository access：**Only select repositories** → 选 `holgeraaa/stock-monitor`
5. Permissions → Repository permissions → **Actions → Read and write**
6. Generate → 复制生成的 `github_pat_xxx`（这就是宏里要填的 token）

> 安全：只给「这一个仓库的 Actions 写权限」的细粒度 token，泄露面极小；只存在你手机里，不进代码、不进仓库。

## 第一步：装 App

应用商店搜 **MacroDroid** 安装（Tasker 也行但更绕，新手用 MacroDroid）。

## 第二步：建宏

1. 打开 MacroDroid → 右下角 **+** → 创建宏
2. **触发条件 (Triggers)** → 搜 `Timer` → 选 **Timer** → Repeat every：**30 minutes** → 确定
3. **动作 (Actions)** → 搜 `HTTP` → 选 **HTTP Request**，填：
   - Method：**POST**
   - URL：`https://api.github.com/repos/holgeraaa/stock-monitor/actions/workflows/monitor.yml/dispatches`
   - Headers（逐行添加）：
     - `Authorization: token <你的 token>`
     - `Accept: application/vnd.github+json`
     - `Content-Type: application/json`
   - Body：`{"ref":"main"}`
   - 确定
4. **约束 (Constraints)**（点右上角约束图标）→ 添加：
   - **Day of Week** → 勾 Mon / Tues / Wed / Thu / Fri
   - **Time of Day** → Between → **09:30** 到 **15:00**
5. 宏命名：`盯盘点火` → 保存

## 第三步：防 MIUI/HyperOS 杀后台（关键，否则到点不触发）

- 手机 **设置 → 应用设置 → 应用管理 → MacroDroid → 电池 → 无限制**
- 同路径 → **自启动 → 允许**
- MacroDroid 内 → **设置 → 勾选「显示持续通知」**（常驻通知防止被回收）
- 若仍漏触发：在动作第一步加一个 **Notification**（空通知）动作唤醒

## 第四步：验证

- **交易时段内**：等一个整点/半点，打开 GitHub（仓库 Actions 页）看是否出现新 run；约 1 分钟内手机收邮件即成功。
- **想立刻测**：临时去掉「Time of Day」约束 → 手动跑一次宏 → 看是否收到邮件 → 再把约束加回。

## 兜底

万一手机没电 / MacroDroid 被系统杀了：随时在对话里说「发一份」，我手动 fire 一次 dispatch。

## 备注

- `nas-trigger/`（T2 Docker 方案）文件保留在仓库，若日后想改走 NAS 可直接用。
- 触发器只是「点火」，改推送逻辑（加飞书、调频率等）都在 `monitor.py`，与手机无关。
