#!/usr/bin/env python3
"""A股盘中盯盘脚本 - 每小时抓取行情数据并通过QQ邮箱发送"""
import smtplib
import json
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import requests

# ===== 配置 =====
QQ_EMAIL = "51568894@qq.com"
QQ_AUTH_CODE = "tgbicxdhkooibiad"
TO_EMAIL = "51568894@qq.com"

# ===== 行情数据抓取 =====
def fetch_market_data():
    """通过公开接口获取大盘行情"""
    data = {
        "time": datetime.now().strftime("%H:%M"),
        "date": datetime.now().strftime("%Y-%m-%d"),
        "sh_index": "获取中",
        "sh_change": "0",
        "sz_index": "获取中",
        "volume": "获取中",
        "leading": [],
        "lagging": [],
        "north_flow": "获取中",
        "stocks": {},
        "advice": "等待数据"
    }
    
    try:
        # 东方财富行情接口
        resp = requests.get(
            "https://push2.eastmoney.com/api/qt/ulist.np/get",
            params={
                "fltt": 2,
                "fields": "f2,f3,f4,f12,f14",
                "secids": "1.000001,0.399001,1.601857,1.600584,0.002156",
            },
            timeout=10
        )
        result = resp.json()
        if result.get("data") and result["data"].get("diff"):
            for item in result["data"]["diff"]:
                code = item.get("f12", "")
                name = item.get("f14", "")
                price = item.get("f2", 0)
                change_pct = item.get("f3", 0)
                
                if code == "000001":
                    data["sh_index"] = f"{price:.0f}" if price else "N/A"
                    data["sh_change"] = f"{change_pct:+.2f}" if change_pct else "0"
                elif code == "399001":
                    data["sz_index"] = f"{price:.0f}" if price else "N/A"
                elif code in ["601857", "600584", "002156"]:
                    data["stocks"][code] = f"{name}={price}({change_pct:+.1f}%)" if price else f"{name}=N/A"
    except Exception as e:
        data["error"] = f"行情接口异常: {str(e)[:50]}"
    
    # 北向资金
    try:
        resp = requests.get(
            "https://push2.eastmoney.com/api/qt/kamt.kline/get",
            params={"fields1": "f1,f3", "fields2": "f2,f4,f6", "klt": "1", "lmt": 1},
            timeout=10
        )
        result = resp.json()
        if result.get("data"):
            net_flow = result["data"].get("s2nNetFlowDay", 0)
            if net_flow:
                data["north_flow"] = f"{net_flow/100000000:+.1f}亿"
    except:
        pass
    
    # 板块数据
    try:
        resp = requests.get(
            "https://push2.eastmoney.com/api/qt/clist/get",
            params={
                "pn": 1, "pz": 5,
                "po": 1, "np": 1,
                "fltt": 2,
                "fid": "f3",
                "fs": "m:90+t2",
                "fields": "f2,f3,f14",
            },
            timeout=10
        )
        result = resp.json()
        if result.get("data") and result["data"].get("diff"):
            for item in result["data"]["diff"][:2]:
                data["leading"].append(f"{item['f14']}({item['f3']:+.1f}%)")
    except:
        pass
    
    try:
        resp = requests.get(
            "https://push2.eastmoney.com/api/qt/clist/get",
            params={
                "pn": 1, "pz": 5,
                "po": 0, "np": 1,
                "fltt": 2,
                "fid": "f3",
                "fs": "m:90+t2",
                "fields": "f2,f3,f14",
            },
            timeout=10
        )
        result = resp.json()
        if result.get("data") and result["data"].get("diff"):
            for item in result["data"]["diff"][:2]:
                data["lagging"].append(f"{item['f14']}({item['f3']:+.1f}%)")
    except:
        pass
    
    # 生成建议
    sh_change_val = float(data["sh_change"]) if data["sh_change"] != "0" else 0
    if sh_change_val > 0.5:
        data["advice"] = "大盘走强 半导体封测持有 油气可分批止盈"
    elif sh_change_val < -0.5:
        data["advice"] = "大盘走弱 减仓至5成以下 封测暂持观望"
    else:
        data["advice"] = "震荡格局 封测持有 油气短线止盈 不追高等回调"
    
    return data


def format_email(data):
    """格式化邮件内容"""
    stocks_str = " ".join(data["stocks"].values()) if data["stocks"] else "标的数据获取中"
    leading_str = " ".join(data["leading"]) if data["leading"] else "获取中"
    lagging_str = " ".join(data["lagging"]) if data["lagging"] else "获取中"
    
    body = f"""沪指{data['sh_index']}({data['sh_change']}%) 深成指{data['sz_index']}
领涨：{leading_str}
领跌：{lagging_str}
北向：{data['north_flow']}
标的：{stocks_str}
建议：{data['advice']}
---
{data['date']} {data['time']} 自动盯盘推送"""
    
    subject = f"【盯盘】{data['time']} 沪指{data['sh_index']} {data['sh_change']}%"
    return subject, body


def send_email(subject, body):
    """通过QQ邮箱SMTP发送邮件"""
    msg = MIMEMultipart()
    msg["From"] = QQ_EMAIL
    msg["To"] = TO_EMAIL
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))
    
    server = smtplib.SMTP("smtp.qq.com", 587, timeout=15)
    server.starttls()
    server.login(QQ_EMAIL, QQ_AUTH_CODE)
    server.sendmail(QQ_EMAIL, TO_EMAIL, msg.as_string())
    server.quit()
    return True


def main():
    print(f"[{datetime.now()}] 开始盯盘...")
    data = fetch_market_data()
    subject, body = format_email(data)
    
    if "error" in data:
        print(f"⚠️ {data['error']}")
    
    try:
        send_email(subject, body)
        print(f"✅ 邮件已发送: {subject}")
    except Exception as e:
        print(f"❌ 发送失败: {e}")
        raise


if __name__ == "__main__":
    main()
