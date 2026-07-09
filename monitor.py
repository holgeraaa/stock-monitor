#!/usr/bin/env python3
"""
A股盘中盯盘脚本 - 炒股养家风格
情绪周期: 冰点 → 试错 → 主升 → 高潮 → 退潮
节奏至上, 不模棱两可, 每句话都是判断
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import requests

# ===== 配置 =====
QQ_EMAIL = "51568894@qq.com"
QQ_AUTH_CODE = "tgbicxdhkooibiad"
TO_EMAIL = "51568894@qq.com"

# ===== 炒股养家风格 - 情绪周期判断 =====

def judge_emotion(data):
    """
    根据盘面数据判断当前情绪周期位置
    返回: (周期, 温度, 一句话判断)
    """
    sh_change = float(data.get("sh_change", 0))
    north = data.get("north_flow", "")
    leading = data.get("leading", [])
    lagging = data.get("lagging", [])
    stocks = data.get("stocks", {})
    hour = datetime.now().hour
    
    # 量化情绪温度 (0-100)
    temp = 50
    if sh_change > 0.8:
        temp += 15
    elif sh_change > 0.3:
        temp += 8
    elif sh_change < -0.8:
        temp -= 15
    elif sh_change < -0.3:
        temp -= 8
    
    # 北向资金影响
    try:
        north_val = float(north.replace("亿", "").replace("+", ""))
        if north_val > 50:
            temp += 10
        elif north_val > 20:
            temp += 5
        elif north_val < -30:
            temp -= 10
        elif north_val < -10:
            temp -= 5
    except:
        pass
    
    # 板块分化判断
    if leading and lagging:
        # 有领涨有领跌 = 结构性行情
        temp += 3
    
    # 判断周期
    if temp >= 70:
        cycle = "主升"
        vibe = "情绪偏热，主线清晰，核心标的可以格局。但高潮不远，别上头追。"
    elif temp >= 55:
        cycle = "修复"
        vibe = "分歧转修复。主线还在，低吸核心，不追杂毛。"
    elif temp >= 40:
        cycle = "分歧"
        vibe = "混沌期。方向不明就等，宁可错过不做错。"
    elif temp >= 25:
        cycle = "退潮"
        vibe = "亏钱效应扩散。减仓、控仓、管住手。"
    else:
        cycle = "冰点"
        vibe = "冰点。恐慌是机会的前夜，但抄底要等放量确认。"
    
    return cycle, temp, vibe


def generate_advice(data, cycle, temp):
    """炒股养家风格操作建议"""
    stocks = data.get("stocks", {})
    leading = data.get("leading", [])
    
    # 板块主线判断
    has_semi = any("半导体" in s or "芯片" in s or "封测" in s for s in leading)
    has_oil = any("油气" in s or "石油" in s or "能源" in s for s in leading)
    
    advice_parts = []
    
    # 情绪周期判断
    if cycle == "主升":
        advice_parts.append("情绪主升期。主线核心拿住，不要被分时震荡洗出去。")
    elif cycle == "修复":
        advice_parts.append("分歧转修复。低吸主线核心，不追高。")
    elif cycle == "分歧":
        advice_parts.append("混沌期。仓位压到5成以下，等方向明朗再加。")
    elif cycle == "退潮":
        advice_parts.append("退潮期。减仓是第一要务，不要和趋势对抗。")
    else:
        advice_parts.append("冰点。等放量阳线确认再动手，现在不是抄底的时候。")
    
    # 板块方向
    if has_semi:
        advice_parts.append("半导体是主线。通富微电、长电科技封测双雄，回调就是机会。")
    if has_oil:
        advice_parts.append("油气受地缘催化，但这是事件驱动不是产业逻辑，短线思维，见好就收。")
    
    # 仓位建议
    if cycle in ("主升", "修复"):
        advice_parts.append("仓位6-7成。")
    elif cycle == "分歧":
        advice_parts.append("仓位4-5成。")
    else:
        advice_parts.append("仓位3成以下。")
    
    return " | ".join(advice_parts)


def generate_vibe_text(data, cycle, temp):
    """生成有盘感的盯盘正文 - 炒股养家风格"""
    sh_idx = data.get("sh_index", "N/A")
    sh_chg = data.get("sh_change", "0")
    sz_idx = data.get("sz_index", "N/A")
    north = data.get("north_flow", "N/A")
    leading = data.get("leading", [])
    lagging = data.get("lagging", [])
    stocks = data.get("stocks", {})
    hour = data.get("hour", datetime.now().hour)
    
    # 标题
    emoji_map = {"主升": "🔥", "修复": "📈", "分歧": "⚡", "退潮": "⚠️", "冰点": "❄️"}
    emoji = emoji_map.get(cycle, "📊")
    subject = f"【盯盘】{emoji}{cycle} 沪指{sh_idx} {sh_chg}%"
    
    # 正文 - 炒股养家风格
    lines = []
    
    # 第一行：核心判断
    if cycle == "主升":
        lines.append(f"情绪主升，温度{temp}。主线明确，不是恐高的时候。")
    elif cycle == "修复":
        lines.append(f"分歧转修复，温度{temp}。方向出来了，低吸核心。")
    elif cycle == "分歧":
        lines.append(f"混沌分歧，温度{temp}。方向不明，仓位先压下来。")
    elif cycle == "退潮":
        lines.append(f"退潮了，温度{temp}。别和趋势对抗，减仓第一。")
    else:
        lines.append(f"冰点，温度{temp}。恐慌在释放，但抄底等放量阳线确认。")
    
    # 第二行：大盘速览
    lines.append(f"沪指{sh_idx}({sh_chg}%) 深成指{sz_idx} 北向{north}")
    
    # 第三行：板块判断
    if leading:
        lead_str = " ".join(leading)
        lines.append(f"主线：{lead_str}")
    if lagging:
        lag_str = " ".join(lagging)
        lines.append(f"回避：{lag_str}")
    
    # 第四行：标的池
    if stocks:
        stock_strs = []
        for code, info in stocks.items():
            stock_strs.append(info)
        lines.append(f"标的：{' | '.join(stock_strs)}")
    
    # 第五行：操作
    advice = generate_advice(data, cycle, temp)
    lines.append(f"操作：{advice}")
    
    # 第六行：养家心法
    quotes = [
        "—— 行情好多做，行情不好少做。",
        "—— 不做杂毛，只做主线。",
        "—— 买入机会，卖出风险。",
        "—— 控制回撤才是复利的核心。",
        "—— 计划你的交易，交易你的计划。",
    ]
    lines.append(quotes[hash(str(temp)) % len(quotes)])
    
    body = "\n".join(lines)
    return subject, body


# ===== 行情数据抓取 =====
def fetch_market_data():
    """通过公开接口获取大盘行情"""
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
    
    # 大盘指数 + 个股
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
    except:
        pass
    
    # 领涨板块
    try:
        resp = requests.get(
            "https://push2.eastmoney.com/api/qt/clist/get",
            params={
                "pn": 1, "pz": 3,
                "po": 1, "np": 1,
                "fltt": 2, "fid": "f3",
                "fs": "m:90+t2",
                "fields": "f2,f3,f14",
            },
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        result = resp.json()
        if result.get("data") and result["data"].get("diff"):
            for item in result["data"]["diff"][:2]:
                data["leading"].append(f"{item['f14']}({item['f3']:+.1f}%)")
    except:
        pass
    
    # 领跌板块
    try:
        resp = requests.get(
            "https://push2.eastmoney.com/api/qt/clist/get",
            params={
                "pn": 1, "pz": 3,
                "po": 0, "np": 1,
                "fltt": 2, "fid": "f3",
                "fs": "m:90+t2",
                "fields": "f2,f3,f14",
            },
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        result = resp.json()
        if result.get("data") and result["data"].get("diff"):
            for item in result["data"]["diff"][:2]:
                data["lagging"].append(f"{item['f14']}({item['f3']:+.1f}%)")
    except:
        pass
    
    return data


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
    now = datetime.now()
    print(f"[{now}] 盯盘启动 - 炒股养家风格")
    
    data = fetch_market_data()
    if "error" in data:
        print(f"⚠️ {data['error']}")
    
    cycle, temp, vibe = judge_emotion(data)
    subject, body = generate_vibe_text(data, cycle, temp)
    
    print(f"情绪周期: {cycle} (温度{temp})")
    print(f"邮件标题: {subject}")
    
    try:
        send_email(subject, body)
        print(f"✅ 已发送")
    except Exception as e:
        print(f"❌ 发送失败: {e}")
        raise


if __name__ == "__main__":
    main()
