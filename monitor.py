#!/usr/bin/env python3
"""
A股盘中盯盘 - 三方交易员联席研判
┌──────────┬─────────────────────────────┐
│ 炒股养家  │ 情绪周期 + 节奏 + 心法          │
│ 花荣      │ 盲点套利 + 市场忽视的机会        │
│ 赵老哥    │ 龙头战法 + 只做最强              │
└──────────┴─────────────────────────────┘
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import requests
import random

# ===== 配置 =====
QQ_EMAIL = "51568894@qq.com"
QQ_AUTH_CODE = "tgbicxdhkooibiad"
TO_EMAIL = "51568894@qq.com"

# ===== 情绪周期判断（共用） =====

def judge_emotion(data):
    sh_change = float(data.get("sh_change", 0))
    north = data.get("north_flow", "")
    leading = data.get("leading", [])
    lagging = data.get("lagging", [])

    temp = 50
    if sh_change > 0.8:   temp += 15
    elif sh_change > 0.3: temp += 8
    elif sh_change < -0.8: temp -= 15
    elif sh_change < -0.3: temp -= 8

    try:
        north_val = float(north.replace("亿", "").replace("+", ""))
        if north_val > 50: temp += 10
        elif north_val > 20: temp += 5
        elif north_val < -30: temp -= 10
        elif north_val < -10: temp -= 5
    except: pass

    if leading and lagging: temp += 3

    if temp >= 70:       cycle = "主升"
    elif temp >= 55:     cycle = "修复"
    elif temp >= 40:     cycle = "分歧"
    elif temp >= 25:     cycle = "退潮"
    else:                cycle = "冰点"

    return cycle, temp


# ===== 炒股养家视角 =====

def yangjia_view(data, cycle, temp):
    """情绪周期 + 节奏判断 + 心法"""
    leading = data.get("leading", [])
    lagging = data.get("lagging", [])
    north = data.get("north_flow", "N/A")

    cycle_map = {
        "主升": (f"温度{temp}，主升期。主线明确，不是恐高的时候。核心拿住，别被分时震下车。"),
        "修复": (f"温度{temp}，分歧转修复。方向出来了，低吸主线核心，不追杂毛。"),
        "分歧": (f"温度{temp}，混沌分歧。方向不明就等，仓位压到5成以下。宁可错过不做错。"),
        "退潮": (f"温度{temp}，退潮了。减仓是第一要务，不要和趋势对抗。"),
        "冰点": (f"温度{temp}，冰点。恐慌在释放，但抄底要等放量阳线确认。现在不是动手的时候。"),
    }

    has_semi = any("半导体" in s or "芯片" in s or "封测" in s for s in leading)
    has_oil = any("油气" in s or "石油" in s for s in leading)

    advice = []
    if has_semi: advice.append("封测双雄通富微电+长电科技，回调就是机会")
    if has_oil: advice.append("油气是事件驱动不是产业逻辑，短线思维")
    if not advice: advice.append("主线不明，多看少动")

    quotes = [
        "行情好多做，行情不好少做。",
        "不做杂毛，只做主线。",
        "买入机会，卖出风险。",
        "控制回撤才是复利的核心。",
    ]

    lines = [
        "━━━ 🎯 炒股养家 · 情绪周期 ━━━",
        cycle_map[cycle],
        f"方向：{' | '.join(advice)}",
        f"仓位：{'6-7成' if cycle in ('主升','修复') else '4-5成' if cycle == '分歧' else '3成以下'}",
        f"心法：{random.choice(quotes)}",
    ]
    return "\n".join(lines)


# ===== 花荣视角 =====

def huarong_view(data, cycle, temp):
    """盲点套利 + 市场忽视的机会"""
    stocks = data.get("stocks", {})
    leading = data.get("leading", [])
    north = data.get("north_flow", "N/A")
    sh_change = float(data.get("sh_change", 0))

    lines = ["━━━ 🦊 花荣 · 盲点套利 ━━━"]
    opportunities = []

    # 中国石油：高股息 + 油价催化，市场忽视的现金牛
    if any("601857" in k for k in stocks):
        oil_info = [v for k, v in stocks.items() if "601857" in k]
        opportunities.append(
            f"中国石油。油价飙6%，12元出头股息率5%+。都盯着科技股，没人看这个现金牛。比理财香。"
        )

    # 封测被低估
    if any("600584" in k for k in stocks) or any("002156" in k for k in stocks):
        opportunities.append(
            f"长电/通富微电。花旗目标价110/80元，先进封装订单排到2027年。市场在炒概念，封测才是实打实出业绩的。"
        )

    # 可转债双低机会
    opportunities.append("可转债ETF(511380)。融资持续净买入，价格中位数不高。攻守兼备，震荡市里的隐形赢家。")

    # 北向资金套利视角
    try:
        nv = float(north.replace("亿", "").replace("+", ""))
        if nv > 30:
            opportunities.append(f"北向净买{north}，外资在偷偷捡筹码。跟着聪明钱走，别逆着来。")
        elif nv < -20:
            opportunities.append(f"北向净卖{north}，聪明钱在撤。别急着抄底，等北向拐头再说。")
    except: pass

    lines.extend(opportunities[:3])  # 最多3条
    return "\n".join(lines)


# ===== 赵老哥视角 =====

def zhaolaoge_view(data, cycle, temp):
    """龙头战法 + 只做最强 + 超短线"""
    leading = data.get("leading", [])
    stocks = data.get("stocks", {})
    sh_change = float(data.get("sh_change", 0))

    lines = ["━━━ ⚔️ 赵老哥 · 龙头战法 ━━━"]

    # 判断最强主线
    has_semi = any("半导体" in s or "芯片" in s for s in leading)
    has_oil = any("油气" in s or "石油" in s for s in leading)

    if has_semi:
        lines.append("半导体是今天最强主线。板块不强我不做，板块强我只做龙头。")
        lines.append("封测双雄通富微电+长电科技，花旗目标价在那摆着。杂毛不碰，只盯龙头。")
    elif has_oil:
        lines.append("油气受地缘催化，中国石油是板块锚。但这种事件驱动持续性存疑，快进快出。")
    else:
        lines.append("今天没有明显主线。没有龙头就休息，钱是等出来的不是做出来的。")

    # 涨停板情绪
    if cycle in ("主升", "修复"):
        lines.append("情绪偏暖，可以适当追确认。但板不够硬就走，别格局。")
    elif cycle == "分歧":
        lines.append("分歧日，打板容易炸。等确定性出来再上，不差这一天。")
    else:
        lines.append("退潮/冰点不做接力。保住本金，等下一个周期。")

    return "\n".join(lines)


# ===== 行情数据抓取 =====

def fetch_market_data():
    now = datetime.now()
    data = {
        "time": now.strftime("%H:%M"),
        "date": now.strftime("%Y-%m-%d"),
        "hour": now.hour,
        "sh_index": "获取中",
        "sh_change": "0",
        "sz_index": "获取中",
        "leading": [],
        "lagging": [],
        "north_flow": "获取中",
        "stocks": {},
    }

    # 大盘 + 个股
    try:
        resp = requests.get(
            "https://push2.eastmoney.com/api/qt/ulist.np/get",
            params={
                "fltt": 2,
                "fields": "f2,f3,f4,f12,f14",
                "secids": "1.000001,0.399001,1.601857,1.600584,0.002156",
            },
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0"}
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
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        result = resp.json()
        if result.get("data"):
            net_flow = result["data"].get("s2nNetFlowDay", 0)
            if net_flow:
                data["north_flow"] = f"{net_flow/100000000:+.1f}亿"
    except: pass

    # 领涨板块
    try:
        resp = requests.get(
            "https://push2.eastmoney.com/api/qt/clist/get",
            params={"pn": 1, "pz": 3, "po": 1, "np": 1, "fltt": 2, "fid": "f3",
                    "fs": "m:90+t2", "fields": "f2,f3,f14"},
            timeout=10, headers={"User-Agent": "Mozilla/5.0"}
        )
        result = resp.json()
        if result.get("data") and result["data"].get("diff"):
            for item in result["data"]["diff"][:2]:
                data["leading"].append(f"{item['f14']}({item['f3']:+.1f}%)")
    except: pass

    # 领跌板块
    try:
        resp = requests.get(
            "https://push2.eastmoney.com/api/qt/clist/get",
            params={"pn": 1, "pz": 3, "po": 0, "np": 1, "fltt": 2, "fid": "f3",
                    "fs": "m:90+t2", "fields": "f2,f3,f14"},
            timeout=10, headers={"User-Agent": "Mozilla/5.0"}
        )
        result = resp.json()
        if result.get("data") and result["data"].get("diff"):
            for item in result["data"]["diff"][:2]:
                data["lagging"].append(f"{item['f14']}({item['f3']:+.1f}%)")
    except: pass

    return data


# ===== 邮件发送 =====

def send_email(subject, body):
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


# ===== 主流程 =====

def main():
    now = datetime.now()
    print(f"[{now}] 盯盘启动 - 三方联席")

    data = fetch_market_data()
    if "error" in data:
        print(f"⚠️ {data['error']}")

    cycle, temp = judge_emotion(data)
    sh_idx = data.get("sh_index", "N/A")
    sh_chg = data.get("sh_change", "0")
    sz_idx = data.get("sz_index", "N/A")
    north = data.get("north_flow", "N/A")
    leading = data.get("leading", [])
    lagging = data.get("lagging", [])
    stocks = data.get("stocks", {})

    # 标题
    emoji = {"主升": "🔥", "修复": "📈", "分歧": "⚡", "退潮": "⚠️", "冰点": "❄️"}.get(cycle, "📊")
    subject = f"【盯盘】{emoji}{cycle} 沪指{sh_idx}{sh_chg}%"

    # 正文 = 大盘速览 + 三个交易员板块
    lead_str = " ".join(leading) if leading else "获取中"
    lag_str = " ".join(lagging) if lagging else "获取中"
    stock_str = " | ".join(stocks.values()) if stocks else "获取中"

    header = f"""══════ 大盘速览 ══════
沪指{sh_idx}({sh_chg}%) 深成指{sz_idx}
北向{north}
领涨：{lead_str}
领跌：{lag_str}
标的：{stock_str}
"""

    body = header + "\n" + yangjia_view(data, cycle, temp) + "\n\n" \
           + huarong_view(data, cycle, temp) + "\n\n" \
           + zhaolaoge_view(data, cycle, temp)

    print(f"情绪周期: {cycle} (温度{temp})")

    try:
        send_email(subject, body)
        print(f"✅ 已发送: {subject}")
    except Exception as e:
        print(f"❌ 发送失败: {e}")
        raise


if __name__ == "__main__":
    main()
