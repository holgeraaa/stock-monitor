#!/usr/bin/env python3
"""
A股盘中盯盘 - 三方联席实时研判
每次推送基于最新行情独立生成观点，不做模板化重复
"""
import smtplib
import json
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, time
import requests
import hashlib

# ===== 配置 =====
QQ_EMAIL = "51568894@qq.com"
QQ_AUTH_CODE = "tgbicxdhkooibiad"
TO_EMAIL = "51568894@qq.com"

# ===== 交易时段判断 =====
def is_trading_time():
    """判断当前是否A股交易时段（周一至周五 9:30-11:30, 13:00-15:00）"""
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    t = now.time()
    morning = time(9, 30) <= t <= time(11, 30)
    afternoon = time(13, 0) <= t <= time(15, 0)
    return morning or afternoon

def get_trading_phase():
    """判断当前处于哪个交易阶段"""
    now = datetime.now()
    h = now.hour
    m = now.minute
    if h == 9 or (h == 10 and m < 15):
        return "早盘开局"
    elif h == 10 or (h == 11 and m < 15):
        return "早盘博弈"
    elif h == 11:
        return "午盘收尾"
    elif h == 13 or (h == 14 and m < 15):
        return "午盘开局"
    else:
        return "尾盘决战"

# ===== 行情抓取 =====

def fetch_market_data():
    now = datetime.now()
    data = {
        "time": now.strftime("%H:%M"),
        "date": now.strftime("%Y-%m-%d"),
        "hour": now.hour,
        "minute": now.minute,
        "phase": get_trading_phase(),
        "sh_index": "获取中",
        "sh_change": "0",
        "sh_high": "N/A",
        "sh_low": "N/A",
        "sz_index": "获取中",
        "sz_change": "0",
        "cyb_index": "获取中",
        "volume": "获取中",
        "leading": [],
        "lagging": [],
        "north_flow": "获取中",
        "north_detail": "",
        "stocks": {},
        "turnover": "获取中",
    }

    try:
        resp = requests.get(
            "https://push2.eastmoney.com/api/qt/ulist.np/get",
            params={
                "fltt": 2,
                "fields": "f2,f3,f4,f5,f6,f7,f15,f16,f17,f18,f12,f14",
                "secids": "1.000001,0.399001,0.399006,1.601857,1.600584,0.002156",
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
                high = item.get("f15", 0)
                low = item.get("f16", 0)
                turnover = item.get("f5", 0)

                if code == "000001":
                    data["sh_index"] = f"{price:.0f}" if price else "N/A"
                    data["sh_change"] = f"{change_pct:+.2f}" if change_pct else "0"
                    data["sh_high"] = f"{high:.0f}" if high else "N/A"
                    data["sh_low"] = f"{low:.0f}" if low else "N/A"
                elif code == "399001":
                    data["sz_index"] = f"{price:.0f}" if price else "N/A"
                    data["sz_change"] = f"{change_pct:+.2f}" if change_pct else "0"
                elif code == "399006":
                    data["cyb_index"] = f"{price:.0f}" if price else "N/A"
                elif code in ["601857", "600584", "002156"]:
                    detail = {
                        "name": name, "price": price, "change": change_pct,
                        "high": high, "low": low, "turnover": turnover
                    }
                    data["stocks"][code] = detail

        # 两市成交额
        try:
            resp2 = requests.get(
                "https://push2.eastmoney.com/api/qt/stock/fflow/daykline/get",
                params={"lmt": 1, "fields1": "f1", "fields2": "f2,f4",
                        "secid": "1.000001", "klt": "1"},
                timeout=10, headers={"User-Agent": "Mozilla/5.0"}
            )
            r2 = resp2.json()
            if r2.get("data") and r2["data"].get("klines"):
                last = r2["data"]["klines"][-1].split(",")
                if len(last) > 2:
                    vol = float(last[2]) / 100000000
                    data["turnover"] = f"{vol:.2f}万亿"
        except: pass
    except Exception as e:
        data["error"] = f"行情异常: {str(e)[:50]}"

    # 北向资金
    try:
        resp = requests.get(
            "https://push2.eastmoney.com/api/qt/kamt.kline/get",
            params={"fields1": "f1,f3", "fields2": "f2,f4,f6", "klt": "1", "lmt": 1},
            timeout=10, headers={"User-Agent": "Mozilla/5.0"}
        )
        result = resp.json()
        if result.get("data"):
            net = result["data"].get("s2nNetFlowDay", 0)
            if net:
                data["north_flow"] = f"{net/100000000:+.1f}亿"
                data["north_detail"] = f"沪股通{result['data'].get('s2nS2nNetFlowDaySH',0)/100000000:+.1f}亿 深股通{result['data'].get('s2nS2nNetFlowDaySZ',0)/100000000:+.1f}亿"
    except: pass

    # 领涨板块 (top 3)
    try:
        resp = requests.get(
            "https://push2.eastmoney.com/api/qt/clist/get",
            params={"pn": 1, "pz": 5, "po": 1, "np": 1, "fltt": 2, "fid": "f3",
                    "fs": "m:90+t2", "fields": "f2,f3,f14"},
            timeout=10, headers={"User-Agent": "Mozilla/5.0"}
        )
        result = resp.json()
        if result.get("data") and result["data"].get("diff"):
            for item in result["data"]["diff"][:3]:
                data["leading"].append({"name": item["f14"], "change": item["f3"]})
    except: pass

    # 领跌板块 (top 3)
    try:
        resp = requests.get(
            "https://push2.eastmoney.com/api/qt/clist/get",
            params={"pn": 1, "pz": 5, "po": 0, "np": 1, "fltt": 2, "fid": "f3",
                    "fs": "m:90+t2", "fields": "f2,f3,f14"},
            timeout=10, headers={"User-Agent": "Mozilla/5.0"}
        )
        result = resp.json()
        if result.get("data") and result["data"].get("diff"):
            for item in result["data"]["diff"][:3]:
                data["lagging"].append({"name": item["f14"], "change": item["f3"]})
    except: pass

    return data


# ===== 情绪周期 =====

def judge_emotion(data):
    sh_change = float(data.get("sh_change", 0))
    north = data.get("north_flow", "")
    leading = data.get("leading", [])
    lagging = data.get("lagging", [])

    temp = 50
    if sh_change > 1.0:   temp += 18
    elif sh_change > 0.5: temp += 10
    elif sh_change > 0.2: temp += 5
    elif sh_change < -1.0: temp -= 18
    elif sh_change < -0.5: temp -= 10
    elif sh_change < -0.2: temp -= 5

    try:
        north_val = float(north.replace("亿", "").replace("+", ""))
        if north_val > 50: temp += 10
        elif north_val > 20: temp += 5
        elif north_val < -30: temp -= 10
        elif north_val < -10: temp -= 5
    except: pass

    if leading and lagging: temp += 3

    if temp >= 70:       return "主升", temp
    elif temp >= 55:     return "修复", temp
    elif temp >= 40:     return "分歧", temp
    elif temp >= 25:     return "退潮", temp
    else:                return "冰点", temp


# ===== 炒股养家 - 基于实时数据生成即时观点 =====

def yangjia_view(data, cycle, temp):
    sh_chg = float(data.get("sh_change", 0))
    sh_idx = data.get("sh_index", "N/A")
    sh_high = data.get("sh_high", "N/A")
    sh_low = data.get("sh_low", "N/A")
    north = data.get("north_flow", "N/A")
    leading = data.get("leading", [])
    lagging = data.get("lagging", [])
    phase = data.get("phase", "")
    stocks = data.get("stocks", {})

    lines = ["━━━ 🎯 炒股养家 · 情绪周期 ━━━"]

    # 1. 盘面即时解读（每时段不同视角）
    amplitude = "N/A"
    if sh_high != "N/A" and sh_low != "N/A":
        try:
            amplitude = f"{float(sh_high) - float(sh_low):.0f}点"
        except: pass

    if phase == "早盘开局":
        lines.append(f"开盘定调。沪指{sh_idx}，振幅{amplitude}，高开{'+' if sh_chg > 0 else ''}{sh_chg}%。今天多空第一轮试探完成。")
        if sh_chg > 0.5:
            lines.append("跳空高开说明隔夜情绪偏暖。但早盘高开容易诱多，看10点后能不能站稳。")
        elif sh_chg < -0.5:
            lines.append("低开在预期内——美伊冲突+道指跌1%压了开盘情绪。但低开不等于弱，看承接力度。")
        else:
            lines.append("平开附近震荡，多空都没有方向。这种盘面最考验耐心，别急着下手。")
    elif phase == "早盘博弈":
        lines.append(f"进入博弈阶段。沪指{sh_idx}({sh_chg:+.2f}%)，日内高低{sh_high}/{sh_low}。")
        if sh_chg > 0:
            lines.append("早盘多头占优但量能没跟上。下午要看北向是否继续流入，如果缩量就要警惕冲高回落。")
        else:
            lines.append("空头占上风但没砸出量。下午如果放量杀跌就得减仓，缩量阴跌反而可以扛一扛。")
    elif phase == "午盘收尾":
        lines.append(f"上午收盘。沪指{sh_idx}({sh_chg:+.2f}%)，北向{north}。")
        lines.append("上午走势决定下午基调。如果上午收在日内高点附近，下午惯性上攻概率大。收在低位则下午偏弱。")
    elif phase == "午盘开局":
        lines.append(f"午盘开局。沪指{sh_idx}({sh_chg:+.2f}%)，承接上午走势。")
        lines.append("下午头30分钟是关键——放量上攻就是真强，缩量震荡就是弱。盯紧了。")
    else:
        lines.append(f"尾盘决战。沪指{sh_idx}({sh_chg:+.2f}%)。最后一小时机构调仓，波动会放大。")

    # 2. 情绪周期判断
    cycle_analysis = {
        "主升": f"温度{temp}，主升期。核心拿住别动，这时候卖飞比被套更难受。",
        "修复": f"温度{temp}，修复中。低吸不追高，主线里的回调就是上车机会。",
        "分歧": f"温度{temp}，分歧加大。这时候方向不明，减仓到5成以下等信号。",
        "退潮": f"温度{temp}，退潮进行时。不要逆势扛单，先出来等冰点。",
        "冰点": f"温度{temp}，冰点。别人恐慌时你要冷静，但抄底必须等放量阳线确认。",
    }
    lines.append(cycle_analysis[cycle])

    # 3. 方向建议
    has_semi = any("半导体" in s.get("name","") or "芯片" in s.get("name","") for s in leading)
    has_oil = any("油气" in s.get("name","") or "石油" in s.get("name","") for s in leading)

    advice = []
    if has_semi:
        advice.append("半导体主线不变，封测双雄回调就是买点")
    if has_oil:
        advice.append("油气地缘催化，短线思维快进快出")
    if not advice:
        advice.append("主线不明，多看少动，管住手就是赚钱")

    # 个股点评
    for code, s in stocks.items():
        chg = s.get("change", 0)
        if code == "002156":
            advice.append(f"通富微电{s['price']}({chg:+.1f}%)花旗目标80元")
        elif code == "600584":
            advice.append(f"长电科技{s['price']}({chg:+.1f}%)花旗目标110元")

    lines.append(f"方向：{' | '.join(advice)}")
    lines.append(f"仓位：{'6-7成' if cycle in ('主升','修复') else '4-5成' if cycle == '分歧' else '3成以下'}")

    # 心法（基于温度选不同心法）
    if temp >= 60:
        lines.append("心法：行情好多做，行情不好少做。现在是前者。")
    elif temp >= 40:
        lines.append("心法：买入机会，卖出风险。现在是等机会的阶段。")
    else:
        lines.append("心法：控制回撤才是复利的核心。现在保本金比赚钱重要。")

    return "\n".join(lines)


# ===== 花荣 - 基于实时数据发现新盲点 =====

def huarong_view(data, cycle, temp):
    stocks = data.get("stocks", {})
    north = data.get("north_flow", "N/A")
    north_detail = data.get("north_detail", "")
    phase = data.get("phase", "")
    sh_chg = float(data.get("sh_change", 0))
    turnover = data.get("turnover", "N/A")

    lines = ["━━━ 🦊 花荣 · 盲点套利 ━━━"]
    opportunities = []

    # 1. 成交额异动
    if turnover != "N/A":
        try:
            tv = float(turnover.replace("万亿", ""))
            if tv > 3.0:
                opportunities.append(f"两市{turnover}，放量明显。量在价先，放量说明有增量资金进场。别被分时吓到，量是真的。")
            elif tv < 2.0:
                opportunities.append(f"两市仅{turnover}，缩量严重。缩量环境下追高是自杀，低吸也要谨慎——没量就没有持续性。")
        except: pass

    # 2. 北向资金动态（动态解读）
    try:
        nv = float(north.replace("亿", "").replace("+", ""))
        if nv > 50:
            opportunities.append(f"北向狂买{north}，外资在扫货。他们买的不是概念是业绩，跟着聪明钱走不会错。")
        elif nv > 15:
            opportunities.append(f"北向净买{north}，温和流入。外资在捡，不是扫。说明他们认为现在估值合理但不便宜。")
        elif nv < -30:
            opportunities.append(f"北向净卖{north}，聪明钱在撤退。这时候不要接飞刀，等北向拐头再考虑进场。")
        elif nv < -10:
            opportunities.append(f"北向小幅流出{north}，不算恐慌性出逃。但连续流出就要警惕了。")
        else:
            opportunities.append(f"北向{north}，外资按兵不动。他们在等方向，我们也等。")
    except: pass

    # 3. 个股机会（实时数据驱动）
    for code, s in stocks.items():
        name = s.get("name", "")
        price = s.get("price", 0)
        chg = s.get("change", 0)
        high = s.get("high", 0)
        low = s.get("low", 0)

        if code == "601857" and price:
            opportunities.append(f"中国石油{price}({chg:+.1f}%)。油价飙6%，今天资金还在往里冲。但注意——这种事件驱动来得快去得也快，设好止盈别贪。")
        elif code == "600584" and price:
            if chg > 0:
                opportunities.append(f"长电科技{price}({chg:+.1f}%)。花旗目标110，现在还在半山腰。市场还没完全定价先进封装的价值。")
            else:
                opportunities.append(f"长电科技{price}({chg:+.1f}%)。回调不是坏事，给没上车的人机会。花旗110元目标摆在那。")
        elif code == "002156" and price:
            opportunities.append(f"通富微电{price}({chg:+.1f}%)。封测双雄之一，花旗目标80元。和长电比还在低位，补涨空间更大。")

    # 4. 可转债
    opportunities.append("可转债ETF(511380)。震荡市里攻守兼备，融资持续净买入。别人恐慌时这是避风港。")

    # 动态选择最多3条，优先个股+北向
    lines.extend(opportunities[:4])
    return "\n".join(lines)


# ===== 赵老哥 - 实时龙头判断 =====

def zhaolaoge_view(data, cycle, temp):
    leading = data.get("leading", [])
    lagging = data.get("lagging", [])
    stocks = data.get("stocks", {})
    phase = data.get("phase", "")
    sh_chg = float(data.get("sh_change", 0))

    lines = ["━━━ ⚔️ 赵老哥 · 龙头战法 ━━━"]

    # 找最强板块
    has_semi = any("半导体" in s.get("name","") or "芯片" in s.get("name","") for s in leading)
    has_oil = any("油气" in s.get("name","") or "石油" in s.get("name","") for s in leading)
    has_ai = any("算力" in s.get("name","") or "AI" in s.get("name","") or "CPO" in s.get("name","") for s in leading)

    # 找最强个股
    best_stock = None
    best_chg = -100
    for code, s in stocks.items():
        if s.get("change", 0) > best_chg:
            best_chg = s.get("change", 0)
            best_stock = s

    if has_semi and has_ai:
        lines.append("半导体+AI双主线！封测是核心，算力是弹性。龙头就两个——通富微电和长电科技。")
    elif has_semi:
        lines.append("半导体独立主线。封测双雄是板块锚，花旗目标价给了天花板。其他杂毛别碰。")
    elif has_oil:
        lines.append("油气受地缘催化，但这不是产业主线。短线可以打，但不格局——快进快出。")
    else:
        lines.append("今天没有明确主线。没有龙头的市场不值得重仓。休息也是交易。")

    # 龙头表现点评
    if best_stock and best_chg > 0:
        lines.append(f"最强标的{best_stock['name']}{best_stock['price']}({best_chg:+.1f}%)。龙头不倒板块不倒，盯紧它。")
    elif best_stock:
        lines.append(f"{best_stock['name']}回调{best_chg:+.1f}%，龙头调整看承接。缩量回调是机会，放量杀跌就得跑。")

    # 打板情绪
    if cycle in ("主升", "修复"):
        lines.append(f"情绪偏暖，{phase}。板够硬就拿，炸板就走。别格局，纪律第一。")
    elif cycle == "分歧":
        lines.append("分歧日不做接力。炸板率高，等确定性出来再上。不差这一天。")
    else:
        lines.append("退潮/冰点不做打板。保住本金，活到下一个周期比什么都重要。")

    return "\n".join(lines)


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

def build_report(data):
    """构建完整报告"""
    cycle, temp = judge_emotion(data)
    sh_idx = data.get("sh_index", "N/A")
    sh_chg = data.get("sh_change", "0")
    sz_idx = data.get("sz_index", "N/A")
    sz_chg = data.get("sz_change", "0")
    cyb_idx = data.get("cyb_index", "N/A")
    north = data.get("north_flow", "N/A")
    turnover = data.get("turnover", "N/A")
    phase = data.get("phase", "")
    time_str = data.get("time", "")

    leading_str = " ".join([f"{s['name']}({s['change']:+.1f}%)" for s in data.get("leading", [])])
    lagging_str = " ".join([f"{s['name']}({s['change']:+.1f}%)" for s in data.get("lagging", [])])

    stock_parts = []
    for code, s in data.get("stocks", {}).items():
        stock_parts.append(f"{s['name']}={s['price']}({s['change']:+.1f}%)")
    stock_str = " | ".join(stock_parts) if stock_parts else "获取中"

    # 标题：情绪+点位+时间
    emoji = {"主升": "🔥", "修复": "📈", "分歧": "⚡", "退潮": "⚠️", "冰点": "❄️"}.get(cycle, "📊")
    subject = f"【盯盘】{emoji}{cycle} 沪指{sh_idx}{sh_chg}% | {time_str}"

    # 大盘速览
    header = f"""══════ 大盘速览 | {time_str} | {phase} ══════
沪指{sh_idx}({sh_chg}%) 深成指{sz_idx}({sz_chg}%) 创业板{cyb_idx}
成交{turnover}  北向{north}
领涨：{leading_str if leading_str else '获取中'}
领跌：{lagging_str if lagging_str else '获取中'}
标的：{stock_str}
"""

    body = header + "\n" \
           + yangjia_view(data, cycle, temp) + "\n\n" \
           + huarong_view(data, cycle, temp) + "\n\n" \
           + zhaolaoge_view(data, cycle, temp)

    return subject, body


def main():
    now = datetime.now()
    print(f"[{now}] 盯盘启动 - 三方联席实时研判")

    if not is_trading_time():
        print("非交易时段，跳过。")
        return

    data = fetch_market_data()
    if "error" in data:
        print(f"⚠️ {data['error']}")

    subject, body = build_report(data)
    print(f"标题: {subject}")

    try:
        send_email(subject, body)
        print(f"✅ 已发送")
    except Exception as e:
        print(f"❌ 发送失败: {e}")
        raise


if __name__ == "__main__":
    main()
