FROM alpine:latest

# curl 用于调 GitHub API；dcron 提供定时；tzdata 让 date 认 Asia/Shanghai
RUN apk add --no-cache curl dcron tzdata \
    && mkdir -p /var/log

# 内核参数关闭（dcron 默认即可），把脚本与 crontab 放进镜像
COPY trigger.sh /usr/local/bin/trigger.sh
RUN chmod +x /usr/local/bin/trigger.sh
COPY crontab /etc/crontabs/root

ENV TZ=Asia/Shanghai

# 前台运行 cron 守护进程，容器才不退出
CMD ["/usr/sbin/crond", "-f", "-l", "2"]
