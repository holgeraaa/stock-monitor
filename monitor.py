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
from datetime import datetime, time, timezone, timedelta
import requests
import hashlib

# 北京时间时区（GitHub Actions 服务器在 UTC，必须显式指定）
BEIJING_TZ = timezone(timedelta(hours=8))
def now_beijing():
    return datetime.now(BEIJING_TZ)

# ===== 配置 =====
QQ_EMAIL = "51568894@qq.com"
QQ_AUTH_CODE = "tgbicxdhkooibiad"
TO_EMAIL = "51568894@qq.com"

# 飞书自定义机器人 Webhook（务必用环境变量传入，勿硬编码进公开仓库）
# 获取方式：飞书群 → 设置 → 群机器人 → 添加机器人 → 自定义机器人 → 复制 Webhook 地址
# 本地测试：export FEISHU_WEBHOOK="https://open.feishu.cn/open-apis/bot/v2/hook/xxxx"
# GitHub 部署：仓库 Settings → Secrets → 新增 FEISHU_WEBHOOK
FEISHU_WEBHOOK = os.environ.get("FEISHU_WEBHOOK", "")
# 飞书是否替代邮件（True=只发飞书, False=邮件+飞书双通道）
FEISHU_ONLY = os.environ.get("FEISHU_ONLY", "false").lower() == "true"

# ===== 模拟仓位（每个交易员3万元，从13:52时点开始） =====
SIM_CAPITAL = 30000
STATE_FILE = "portfolio_state.json"
CYCLE_ORDER = {"冰点": 0, "退潮": 1, "分歧": 2, "修复": 3, "主升": 4}
# T+1 约束：今天买入的股数锁在 buy_locked 字段，当日不可卖；跨日自动解锁
TRADE_DATE = now_beijing().strftime("%Y%m%d")

import json
import os

def load_state():
    """加载模拟仓位状态"""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

def save_state(state):
    """保存模拟仓位状态"""
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def simulate_decision(trader_key, trader, cycle, stocks_data):
    """
    模拟交易员加仓/减仓决策（遵守 A 股 T+1 规则）
    - 今天买入的股数存入 buy_locked 字段，当日不可卖出
    - 减仓时只卖 lock-free 部分
    - 跨日自动解锁（trade_date 变了就清空 buy_locked）
    返回: (决策文本, 是否变更)
    """
    last_cycle = trader.get("last_cycle", "分歧")
    last_level = CYCLE_ORDER.get(last_cycle, 2)
    curr_level = CYCLE_ORDER.get(cycle, 2)

    # T+1：检查是否跨日，跨日则解锁所有 buy_locked
    trader_date = trader.get("trade_date", "")
    if trader_date != TRADE_DATE:
        for code in list(trader.get("buy_locked", {}).keys()):
            trader["buy_locked"][code] = 0
        trader["trade_date"] = TRADE_DATE

    decision = "持仓不动"
    changed = False

    # 情绪升温 → 加仓
    if curr_level > last_level and trader["cash"] > 1000:
        # 选最强持仓加仓，或用现金买首选标的
        best_code = None
        best_chg = -100
        for code, pos in trader["positions"].items():
            chg = stocks_data.get(code, {}).get("change", 0)
            if chg > best_chg:
                best_chg = chg
                best_code = code

        if best_code:
            price = stocks_data.get(best_code, {}).get("price", 0) or trader["positions"][best_code]["cost"]
            buy_amount = min(trader["cash"] * 0.5, 5000)
            shares = int(buy_amount // price // 100) * 100  # 整百股
            if shares >= 100:
                cost = shares * price
                trader["cash"] -= cost
                pos = trader["positions"][best_code]
                # 更新加权成本
                total_shares = pos["shares"] + shares
                pos["cost"] = (pos["shares"] * pos["cost"] + cost) / total_shares
                pos["shares"] = total_shares
                # T+1：锁仓
                locked = trader.setdefault("buy_locked", {}).get(best_code, 0)
                trader["buy_locked"][best_code] = locked + shares
                decision = f"加仓 | {pos['name']}买{shares}股@{price:.2f} [T+1锁仓]"
                changed = True
            else:
                decision = "持仓不动(现金不足1手)"

    # 情绪降温 → 减仓（只卖 lock-free 部分，遵守 T+1）
    elif curr_level < last_level:
        # 找最弱持仓（且减去锁仓后仍有可卖）
        weak_code = None
        weak_chg = 100
        for code, pos in trader["positions"].items():
            locked = trader.get("buy_locked", {}).get(code, 0)
            available = pos["shares"] - locked
            if available < 100:
                continue  # 锁仓后无可卖整手
            chg = stocks_data.get(code, {}).get("change", 0)
            if chg < weak_chg:
                weak_chg = chg
                weak_code = code

        if weak_code:
            price = stocks_data.get(weak_code, {}).get("price", 0) or trader["positions"][weak_code]["cost"]
            pos = trader["positions"][weak_code]
            locked = trader.get("buy_locked", {}).get(weak_code, 0)
            available = pos["shares"] - locked
            sell_shares = int(available * 0.3 / 100) * 100
            if sell_shares >= 100:
                trader["cash"] += sell_shares * price
                pos["shares"] -= sell_shares
                decision = f"减仓 | {pos['name']}卖{sell_shares}股@{price:.2f} [T+1: 锁{locked}股不可卖]"
                changed = True
                if pos["shares"] == 0:
                    del trader["positions"][weak_code]
                    trader.setdefault("buy_locked", {}).pop(weak_code, None)

    trader["last_cycle"] = cycle
    return decision, changed


def calc_trader_pnl(trader_key, stocks_data, state):
    """计算交易员当前持仓盈亏"""
    trader = state["traders"].get(trader_key)
    if not trader:
        return None

    total_value = trader["cash"]
    position_detail = []

    for code, pos in trader["positions"].items():
        current = stocks_data.get(code, {})
        price = current.get("price", 0)
        if not price:
            price = pos["cost"]

        market_value = pos["shares"] * price
        cost_value = pos["shares"] * pos["cost"]
        pnl = market_value - cost_value
        pnl_pct = (price / pos["cost"] - 1) * 100

        total_value += market_value
        position_detail.append({
            "code": code,
            "name": pos["name"],
            "shares": pos["shares"],
            "cost": pos["cost"],
            "price": price,
            "market_value": market_value,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
        })

    total_pnl = total_value - SIM_CAPITAL
    total_pnl_pct = total_pnl / SIM_CAPITAL * 100

    return {
        "name": trader["name"],
        "cash": trader["cash"],
        "total_value": total_value,
        "total_pnl": total_pnl,
        "total_pnl_pct": total_pnl_pct,
        "positions": position_detail,
    }


# ===== 交易时段判断 =====
def is_trading_time():
    """判断当前是否A股交易时段（周一至周五 9:30-11:30, 13:00-15:00）北京时间"""
    now = now_beijing()
    if now.weekday() >= 5:
        return False
    t = now.time()
    morning = time(9, 30) <= t <= time(11, 30)
    afternoon = time(13, 0) <= t <= time(15, 0)
    return morning or afternoon

def get_trading_phase():
    """判断当前处于哪个交易阶段（北京时间）"""
    now = now_beijing()
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
    now = now_beijing()
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
                "secids": "1.000001,0.399001,0.399006,1.601857,1.600584,0.002156,0.159949",
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
                elif code in ["601857", "600584", "002156", "159949"]:
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


# ===== 研究员视角 =====

def zhangyidong_view(data, cycle, temp):
    """张忆东 - 兴业证券，港美股+科技成长，全球视野核心资产"""
    leading = data.get("leading", [])
    stocks = data.get("stocks", {})
    north = data.get("north_flow", "N/A")
    sh_chg = float(data.get("sh_change", 0))
    phase = data.get("phase", "")

    lines = ["━━━ 🌏 张忆东 · 全球视野 ━━━"]

    # 科技成长主线判断
    has_semi = any("半导体" in s.get("name","") or "芯片" in s.get("name","") for s in leading)
    has_ai = any("算力" in s.get("name","") or "AI" in s.get("name","") or "CPO" in s.get("name","") for s in leading)

    lines.append("全球流动性拐点临近，科技成长是穿越周期的主线。现在不是要不要配科技的问题，是怎么配的问题。")
    if has_semi:
        lines.append("半导体国产化是确定性最强的长逻辑。长鑫科技IPO是里程碑——DRAM从0到全球第四，这不是短期情绪是产业趋势。")
    if has_ai:
        lines.append("算力是新时代的电力。AI应用落地速度超预期，硬件基础设施需求刚性。这个赛道能看3-5年。")
    else:
        lines.append("科技股短期震荡正常，核心资产回调就是上车机会。别看分时，看产业趋势。")

    # 个股观点
    for code, s in stocks.items():
        if code in ("002156", "600584"):
            lines.append(f"{s['name']}{s['price']}({s['change']:+.1f}%)。先进封装是AI算力的瓶颈环节，订单排到2027年不是吹的。这是核心资产里的核心。")

    # 港股/A股联动
    lines.append("港股科技昨天涨近5%，这是全球资金对中国科技资产的重新定价。A股半导体会跟随这个逻辑。")

    return "\n".join(lines)


def xunyugen_view(data, cycle, temp):
    """荀玉根 - 海通证券策略首席，市场趋势判断+行业配置"""
    leading = data.get("leading", [])
    lagging = data.get("lagging", [])
    stocks = data.get("stocks", {})
    sh_chg = float(data.get("sh_change", 0))
    north = data.get("north_flow", "N/A")
    turnover = data.get("turnover", "N/A")
    phase = data.get("phase", "")

    lines = ["━━━ 📈 荀玉根 · 策略配置 ━━━"]

    # 市场趋势判断（基于数据）
    lines.append(f"现在是震荡市的修复阶段。沪指{data.get('sh_index')}({sh_chg:+.2f}%)，{phase}。")

    # 行业配置建议
    has_semi = any("半导体" in s.get("name","") or "芯片" in s.get("name","") for s in leading)
    has_oil = any("油气" in s.get("name","") or "石油" in s.get("name","") for s in leading)

    config = []
    if has_semi:
        config.append("科技（半导体/AI）是第一配置方向，业绩兑现+政策催化")
    if has_oil:
        config.append("能源是阶段性对冲，地缘不确定性下的防守选择")
    config.append("高股息（银行/石油）是底仓，震荡市提供安全垫")

    lines.append(f"行业配置：{' > '.join(config)}")

    # 量能判断
    if turnover != "N/A":
        try:
            tv = float(turnover.replace("万亿", ""))
            if tv > 2.5:
                lines.append(f"两市{turnover}活跃，量价配合良好。这种环境下持股待涨比频繁交易更划算。")
            else:
                lines.append(f"两市{turnover}，量能不足。控制仓位，等放量确认方向。")
        except: pass

    # 北向
    try:
        nv = float(north.replace("亿", "").replace("+", ""))
        if nv > 0:
            lines.append(f"北向{north}，外资配置型资金在流入，中期趋势偏多。")
        else:
            lines.append(f"北向{north}，短期有扰动但不改中期逻辑。")
    except: pass

    return "\n".join(lines)


def gaoshanwen_view(data, cycle, temp):
    """高善文 - 安信证券，学院派，市场水位+数据驱动"""
    leading = data.get("leading", [])
    lagging = data.get("lagging", [])
    sh_idx = data.get("sh_index", "N/A")
    sh_chg = float(data.get("sh_change", 0))
    north = data.get("north_flow", "N/A")
    turnover = data.get("turnover", "N/A")

    lines = ["━━━ 🔬 高善文 · 市场水位 ━━━"]

    # 市场水位判断
    lines.append(f"沪指{sh_idx}点，市场水位处于合理区间。现在的光线很好，没有系统性风险但需要耐心。")

    # 基本面驱动
    lines.append("经济数据在筑底，PMI连续4个月站荣枯线上。分子端（企业盈利）在改善，这是市场最坚实的支撑。")

    # 流动性
    try:
        nv = float(north.replace("亿", "").replace("+", ""))
        if nv > 0:
            lines.append(f"北向{north}，外资用脚投票。全球配置型资金在增配中国资产，这是长期趋势。")
        else:
            lines.append(f"北向{north}，短期扰动不改外资中期流入的大方向。")
    except: pass

    # 结构性机会
    has_semi = any("半导体" in s.get("name","") or "芯片" in s.get("name","") for s in leading)
    if has_semi:
        lines.append("半导体国产化是经济结构转型的核心抓手。这不是主题炒作是产业升级，看长做长。")
    else:
        lines.append("市场缺乏明确主线时，高股息是穿越震荡的最佳选择。")

    # 波动率预期
    lines.append("市场波动率处于低位，这种环境下持股比择时更重要。频繁交易只会贡献摩擦成本。")

    return "\n".join(lines)


def fupeng_view(data, cycle, temp):
    """付鹏 - 东北证券，全球宏观+大类资产，犀利直白"""
    leading = data.get("leading", [])
    stocks = data.get("stocks", {})
    sh_chg = float(data.get("sh_change", 0))
    north = data.get("north_flow", "N/A")
    phase = data.get("phase", "")

    lines = ["━━━ 💰 付鹏 · 全球宏观 ━━━"]

    # 美伊/油价视角（直接关联油气仓位）
    lines.append("美伊冲突升级，油价飙6%。这不是短期脉冲是中期变量——霍尔木兹海峡通航风险溢价会持续计入。")

    # 你的油气仓位点评
    for code, s in stocks.items():
        if code == "601857":
            if s.get("change", 0) > 0:
                lines.append(f"中国石油{s['price']}({s['change']:+.1f}%)。油价逻辑很硬，但注意——地缘溢价随时可能因谈判消息回落。设好止盈，别把事件驱动当成长股拿。")
            else:
                lines.append(f"中国石油{s['price']}({s['change']:+.1f}%)。油价还在高位，股价回调是预期差。但这类标的估值天花板低，赚的是价差不是复利。")

    # 全球流动性
    lines.append("美联储政策转向是下半年最大变量。流动性宽松预期支撑风险资产，但节奏比方向更重要。")

    # 北向/外资
    try:
        nv = float(north.replace("亿", "").replace("+", ""))
        if nv > 30:
            lines.append(f"北向净买{north}。外资在做多中国资产，但别盲目跟随——他们的久期和我们不一样。")
        elif nv < -20:
            lines.append(f"北向净卖{north}。聪明钱在撤退，市场情绪可能比盘面显示的更脆弱。")
        else:
            lines.append(f"北向{north}。外资中性，等待更明确的信号。")
    except: pass

    # 风险警示
    lines.append("风险提示：A股散户化特征明显，情绪驱动波动大。仓位管理比选股更重要——这是散户唯一能战胜机构的武器。")

    return "\n".join(lines)


# ===== 老艾（艾堂明） - 财经评论员，散户视角 =====

def laoai_view(data, cycle, temp):
    """老艾 - 独立财经评论员，微博大V，散户视角，接地气"""
    leading = data.get("leading", [])
    lagging = data.get("lagging", [])
    stocks = data.get("stocks", {})
    sh_chg = float(data.get("sh_change", 0))
    north = data.get("north_flow", "N/A")
    phase = data.get("phase", "")

    lines = ["━━━ 📢 老艾 · 散户视角 ━━━"]

    # 开盘/盘中白话解读
    if sh_chg > 0.5:
        lines.append(f"今天大盘{sh_chg:+.2f}%，红彤彤的。但别高兴太早——账户回本了吗？没回本就是假涨。")
    elif sh_chg < -0.5:
        lines.append(f"又绿了{sh_chg:+.2f}%？别慌，跌下来才有便宜筹码捡。但别急着抄底，等企稳信号。")
    else:
        lines.append(f"大盘{sh_chg:+.2f}%，不死不活。这种行情最磨人，管住手别乱动。")

    # 板块大白话
    has_semi = any("半导体" in s.get("name","") or "芯片" in s.get("name","") for s in leading)
    has_oil = any("油气" in s.get("name","") or "石油" in s.get("name","") for s in leading)

    if has_semi:
        lines.append("半导体今天又支棱起来了。长鑫科技IPO这个事不是一天两天的利好，是产业大逻辑。但别追高，回调买更舒服。")
    if has_oil:
        lines.append("油气涨是因为打仗。这种钱不好赚——消息一来就跌，散户永远是最后知道的。赚了就跑别恋战。")

    # 个股白话
    for code, s in stocks.items():
        if code in ("002156", "600584"):
            lines.append(f"{s['name']}{s['price']}({s['change']:+.1f}%)。花旗给的目标价摆在那，说明机构中长期看好。但咱小散别全仓干，分批买。")
        elif code == "601857":
            lines.append(f"中国石油{s['price']}({s['change']:+.1f}%)。大块头涨起来慢但稳，适合当压舱石。股息率5%比存银行强。")

    # 给散户的忠告
    lines.append("给散户一句话：别人贪婪我恐惧，别人恐惧我贪婪。但大部分人做不到——因为大部分人没有仓位管理意识。")

    return "\n".join(lines)


# ===== 模拟仓位汇总 =====

def sim_portfolio_view(stocks_data, cycle):
    """生成三个交易员的模拟仓位盈亏汇总 + 加仓减仓决策"""
    state = load_state()
    if not state:
        return "━━━ 💼 模拟仓位 ━━━\n状态文件缺失"

    lines = [f"━━━ 💼 模拟仓位实况（每人均3万 | 起始{state.get('init_time','')}） ━━━"]

    decisions = {}
    for trader_key in ["yangjia", "huarong", "zhaolaoge"]:
        trader = state["traders"].get(trader_key)
        if not trader:
            continue
        decision, changed = simulate_decision(trader_key, trader, cycle, stocks_data)
        decisions[trader_key] = decision

    # 回写状态（加仓减仓已生效）
    save_state(state)

    for trader_key in ["yangjia", "huarong", "zhaolaoge"]:
        result = calc_trader_pnl(trader_key, stocks_data, state)
        if not result:
            continue

        trader = state["traders"].get(trader_key, {})
        locked = trader.get("buy_locked", {})

        pnl_sign = "+" if result["total_pnl"] >= 0 else ""
        lines.append(f"\n【{result['name']}】 总资产{result['total_value']:.0f}元 ({pnl_sign}{result['total_pnl']:.0f}元, {pnl_sign}{result['total_pnl_pct']:.2f}%)")
        lines.append(f"  📌 操作: {decisions[trader_key]}")

        for pos in result["positions"]:
            p_sign = "+" if pos["pnl"] >= 0 else ""
            lock = locked.get(pos["code"], 0)
            t1_tag = f" [T+1锁{lock}股]" if lock > 0 else ""
            lines.append(f"  {pos['name']}({pos['code']}): {pos['shares']}股{t1_tag} @成本{pos['cost']:.2f} → 现价{pos['price']:.2f} | 市值{pos['market_value']:.0f} | {p_sign}{pos['pnl']:.0f}元({p_sign}{pos['pnl_pct']:.1f}%)")

        lines.append(f"  现金: {result['cash']:.0f}元")

    return "\n".join(lines)


# ===== 用户持仓 + 七方建议 =====

def user_holding_view(data, cycle, temp):
    """用户持仓(159949创业板50ETF 17000份) + 七方建议"""
    state = load_state()
    user = state.get("user", {}) if state else {}
    positions = user.get("positions", {})

    lines = ["━━━ 👤 你的持仓 | 159949创业板50ETF ━━━"]

    # 持仓盈亏
    for code, pos in positions.items():
        current = data.get("stocks", {}).get(code, {})
        price = current.get("price", 0) or pos["cost"]
        chg = current.get("change", 0)
        market_value = pos["shares"] * price
        cost_value = pos["shares"] * pos["cost"]
        pnl = market_value - cost_value
        pnl_pct = (price / pos["cost"] - 1) * 100
        p_sign = "+" if pnl >= 0 else ""

        lines.append(f"持有{pos['shares']}份 @成本{pos['cost']:.2f} → 现价{price:.3f}({chg:+.2f}%)")
        lines.append(f"市值{market_value:.0f}元 | 盈亏{p_sign}{pnl:.0f}元({p_sign}{pnl_pct:.2f}%)")

    # 七方建议
    etf_chg = data.get("stocks", {}).get("159949", {}).get("change", 0)
    cyb = data.get("cyb_index", "N/A")
    sh_chg = float(data.get("sh_change", 0))

    advice_map = {
        "yangjia": f"炒股养家：创业板弹性大，{etf_chg:+.1f}%不算极端。情绪{cycle}，仓位不重就拿着，别在分歧日割肉。",
        "huarong": f"花荣：创业板50是进攻品种不是底仓。现在{etf_chg:+.1f}%，没破位就持有，但别加仓——这只ETF波动比你那几个主板票大得多。",
        "zhaolaoge": f"赵老哥：创业板50不是龙头是篮子。想做弹性可以，但设好止损位，跌破成本3%就走，别扛。",
        "zhangyidong": f"张忆东：创业板50代表新经济成长，中长期逻辑在。但短期受美联储流动性影响大，{etf_chg:+.1f}%正常波动，逢跌分批比一把梭舒服。",
        "xunyugen": f"荀玉根：创业板50仓位建议控制在总资产20%以内。当前{etf_chg:+.1f}%，如果仓位不重可以持有，权重股企稳后创业板弹性会出来。",
        "gaoshanwen": f"高善文：创业板估值分位不低，但盈利在改善。持有可以，别追高——这种高贝塔品种最适合的是低位布局不是高位追。",
        "fupeng": f"付鹏：创业板50对流动性最敏感。美联储转向前波动会放大。你这1.7万份也就3万多块，亏得起就拿着，但别把它当稳健资产。",
        "laoai": f"老艾：创业板ETF散户最爱买，因为便宜门槛低。但记住——它涨起来猛跌起来也猛。{etf_chg:+.1f}%今天还行，设个止盈点别贪。",
    }

    lines.append("")
    lines.append("📋 七方建议：")
    for key, adv in advice_map.items():
        lines.append(f"  · {adv}")

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


# ===== 飞书机器人推送 =====

def chunk_text(text, limit=1800):
    """把超长文本按换行切分为不超过 limit 字符的块（避免飞书单条消息超限）"""
    if len(text) <= limit:
        return [text]
    lines = text.split("\n")
    chunks, cur = [], ""
    for ln in lines:
        if len(cur) + len(ln) + 1 > limit and cur:
            chunks.append(cur)
            cur = ln
        else:
            cur = (cur + "\n" + ln) if cur else ln
    if cur:
        chunks.append(cur)
    return chunks


def send_feishu(body, subject=""):
    """通过飞书自定义机器人推送。按板块拆分多条消息，单条超长再切块。返回是否成功。"""
    if not FEISHU_WEBHOOK:
        print("⚠️ 未配置 FEISHU_WEBHOOK，跳过飞书推送")
        return False

    # 按行归并：行首为分隔符（━━━ 或 ═════）即开启新板块，标题与正文合为一条
    sections, cur = [], []
    for ln in body.split("\n"):
        if ln.startswith("━━━") or ln.startswith("══════"):
            if cur:
                sections.append("\n".join(cur).strip("\n"))
            cur = [ln]
        else:
            cur.append(ln)
    if cur:
        sections.append("\n".join(cur).strip("\n"))
    sections = [s for s in sections if s.strip()]

    ok = True
    for i, sec in enumerate(sections):
        text = (subject + "\n\n" + sec) if i == 0 else sec
        for chunk in chunk_text(text, 1800):
            payload = {"msg_type": "text", "content": {"text": chunk}}
            try:
                resp = requests.post(FEISHU_WEBHOOK, json=payload, timeout=10)
                rj = resp.json()
                if rj.get("code", 0) != 0:
                    print(f"❌ 飞书推送被拒: {rj}")
                    ok = False
            except Exception as e:
                print(f"❌ 飞书推送异常: {e}")
                ok = False
    return ok


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
           + sim_portfolio_view(data.get("stocks", {}), cycle) + "\n\n" \
           + user_holding_view(data, cycle, temp) + "\n\n" \
           + yangjia_view(data, cycle, temp) + "\n\n" \
           + huarong_view(data, cycle, temp) + "\n\n" \
           + zhaolaoge_view(data, cycle, temp) + "\n\n" \
           + zhangyidong_view(data, cycle, temp) + "\n\n" \
           + xunyugen_view(data, cycle, temp) + "\n\n" \
           + gaoshanwen_view(data, cycle, temp) + "\n\n" \
           + fupeng_view(data, cycle, temp) + "\n\n" \
           + laoai_view(data, cycle, temp)

    return subject, body


def main():
    now = now_beijing()
    print(f"[{now}] 盯盘启动 - 七方联席实时研判")

    if not is_trading_time():
        print("非交易时段，跳过。")
        return

    data = fetch_market_data()
    if "error" in data:
        print(f"⚠️ {data['error']}")

    subject, body = build_report(data)
    print(f"标题: {subject}")

    # 双通道推送：邮件 + 飞书（任一成功即视为送达）
    email_ok = feishu_ok = False

    if not FEISHU_ONLY:
        try:
            send_email(subject, body)
            email_ok = True
            print("✅ 邮件已发送")
        except Exception as e:
            print(f"❌ 邮件发送失败: {e}")

    try:
        feishu_ok = send_feishu(body, subject)
        if feishu_ok:
            print("✅ 飞书已推送")
        elif FEISHU_ONLY:
            print("❌ 飞书推送失败")
    except Exception as e:
        print(f"❌ 飞书推送异常: {e}")

    if not email_ok and not feishu_ok:
        raise SystemExit("❌ 所有推送渠道均失败")


if __name__ == "__main__":
    main()
