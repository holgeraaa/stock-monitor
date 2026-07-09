# 小米手机 Termux 触发器部署指南（开源 / token 仅存本机）

> 全程开源：Termux 是开源终端，trigger.sh 是你亲手看的脚本，GitHub token 只存在你手机
> 的 `~/.github_token`（权限 600），没有任何闭源自动化 App 碰你的凭证。
> 手机只负责「每30分钟 POST 调 GitHub」，抓行情+发邮件都在云端完成。

## 第零步：拿一个 scoped GitHub Token（只需一次）

GitHub → 头像 → Settings → Developer settings → Personal access tokens → **Fine-grained tokens** → Generate：
- 名称：`stock-monitor-termux`
- Repository access：**Only select repositories** → 选 `holgeraaa/stock-monitor`
- Permissions → Repository permissions → **Actions → Read and write**
- 复制 `github_pat_xxx`（下面要写进手机文件）

## 第一步：装 Termux（务必用 F-Droid 版）

- 从 **F-Droid** 搜 **Termux** 安装（⚠️ 别用 Google Play 版，已停更且受限）
- 可选装 **Termux:Boot**（用于开机自启 crond，F-Droid 同样有）

## 第二步：在 Termux 里装依赖

```bash
pkg update -y
pkg install -y curl cronie termux-services tzdata
```

## 第三步：放入 token（只存本机，权限收紧）

```bash
echo '你的github_pat_xxx' > ~/.github_token
chmod 600 ~/.github_token
```
> 把 `你的github_pat_xxx` 换成第零步复制的 token。

## 第四步：放入脚本

把本仓库 `termux-trigger/trigger.sh` 的内容复制到手机：

```bash
nano ~/trigger.sh
# 粘贴 trigger.sh 内容，Ctrl+X → Y 保存
chmod +x ~/trigger.sh
```

（或从仓库拉取：`curl -O https://raw.githubusercontent.com/holgeraaa/stock-monitor/main/termux-trigger/trigger.sh && chmod +x ~/trigger.sh`）

## 第五步：启 crond 并设为开机自启

```bash
sv-enable crond     # 开机自启（需 Termux:Boot 配合）
sv up crond         # 立即启动
```

## 第六步：加 crontab（每30分钟，UTC 1-7 点覆盖北京 9-15 点，仅工作日）

```bash
(crontab -l 2>/dev/null; echo '*/30 1-7 * * 1-5 $HOME/trigger.sh >> $HOME/trigger.log 2>&1') | crontab -
```

> 脚本内部还会再判一次北京时间交易时段，双保险。

## 第七步：防 MIUI/HyperOS 杀后台（关键）

- 手机 **设置 → 应用设置 → 应用管理 → Termux → 电池 → 无限制**
- 同路径 → **自启动 → 允许**
- 若装了 **Termux:Boot**，同样设为「无限制 + 自启动」，否则重启后 crond 起不来
- Termux 内保持一个会话常驻（或依赖 termux-services 后台 daemon），MIUI 才不会回收

## 第八步：验证

```bash
~/trigger.sh          # 交易时段应打印 [点火] -> HTTP 204；非交易时段打印 [跳过]
cat ~/trigger.log     # 查看历史触发记录
```

- 交易时段内等一个整点/半点，打开 GitHub（仓库 Actions 页）应出现新 run，约 1 分钟手机收邮件。
- 想立刻测：临时把 crontab 里的时间范围放宽，或手动多跑几次 `~/trigger.sh`，看邮件是否到达，再改回。

## 安全小结

- Termux 开源，脚本逐行可见，无黑盒逻辑。
- token 仅在 `~/.github_token`（600），不进代码、不进仓库、不上传任何第三方。
- 即便用细粒度单仓 token，手机丢失/被入侵，泄露面也只是「触发这一个人仓库的工作流」。
- 兜底：手机没电或被杀，随时在对话里说「发一份」，我手动 fire 一次。

## 备注

- `phone-trigger-guide.md`（MacroDroid 版）保留作备选参考。
- `nas-trigger/`（T2 Docker 版）同样保留。
