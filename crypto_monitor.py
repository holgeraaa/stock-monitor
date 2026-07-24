#!/usr/bin/env python3
"""
BTC/ETH 关键位置盯盘推送
每天早中晚各一次，从 Binance 抓 K线数据，自己算技术指标，标注支撑/阻力/操作建议
复用 monitor.py 的 QQ 邮箱配置
"""
import smtplib
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone, timedelta
import requests

# 北京时间（GitHub Actions 服务器在 UTC，必须显式指定）
BEIJING_TZ = timezone(timedelta(hours=8))
def now_beijing():
    return datetime.now(BEIJING_TZ)

# ===== 配置（复用 A 股 monitor.py 的邮箱） =====
QQ_EMAIL = "51568894@qq.com"
QQ_AUTH_CODE = "tgbicxdhkooibiad"
TO_EMAIL = "51568894@qq.com"

# ===== 数据源（多 fallback：Binance主域 → Binance.us → Coinbase → CoinCap） =====
HEADERS = {"User-Agent": "Mozilla/5.0"}

# 币种配置
COINS = {
    "BTC": {"symbol": "BTCUSDT", "name": "比特币", "decimals": 0, "coingecko_id": "bitcoin", "coinbase": "BTC-USD"},
    "ETH": {"symbol": "ETHUSDT", "name": "以太坊", "decimals": 2, "coingecko_id": "ethereum", "coinbase": "ETH-USD"},
}


def fetch_klines(coin_key, limit=220):
    """
    多数据源 fallback 抓取日线 K线
    返回: list of [timestamp, open, high, low, close, volume]
    """
    cfg = COINS[coin_key]

    # 源1: Binance 主域
    try:
        resp = requests.get(
            "https://api.binance.com/api/v3/klines",
            params={"symbol": cfg["symbol"], "interval": "1d", "limit": limit},
            timeout=10, headers=HEADERS,
        )
        if resp.status_code == 200:
            return resp.json()
    except:
        pass

    # 源2: Binance.us 备用
    try:
        resp = requests.get(
            "https://api.binance.us/api/v3/klines",
            params={"symbol": cfg["symbol"], "interval": "1d", "limit": limit},
            timeout=10, headers=HEADERS,
        )
        if resp.status_code == 200:
            return resp.json()
    except:
        pass

    # 源3: Coinbase Exchange API（美国合规，GitHub 可访问）
    try:
        resp = requests.get(
            f"https://api.exchange.coinbase.com/products/{cfg['coinbase']}/candles",
            params={"granularity": 86400},
            timeout=10, headers=HEADERS,
        )
        if resp.status_code == 200:
            data = resp.json()
            # Coinbase 返回 [time, low, high, open, close, volume]，需转成 Binance 格式
            klines = []
            for row in sorted(data[-limit:], key=lambda x: x[0]):
                klines.append([row[0]*1000, str(row[3]), str(row[2]), str(row[1]), str(row[4]), str(row[5])])
            return klines
    except:
        pass

    # 源4: CoinCap（纯价格历史，无OHLC，用close模拟）
    try:
        resp = requests.get(
            f"https://api.coincap.io/v2/assets/{cfg['coingecko_id']}/history",
            params={"interval": "d1"},
            timeout=10, headers=HEADERS,
        )
        if resp.status_code == 200:
            data = resp.json().get("data", [])
            klines = []
            for item in data[-limit:]:
                ts = int(item.get("time", 0))
                price = float(item.get("priceUsd", 0))
                if price:
                    klines.append([ts*1000, str(price), str(price), str(price), str(price), "0"])
            return klines
    except:
        pass

    return None


def calc_sma(closes, period):
    """简单移动平均"""
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / period


def calc_ema(closes, period):
    """指数移动平均"""
    if len(closes) < period:
        return None
    multiplier = 2 / (period + 1)
    ema = sum(closes[:period]) / period  # 初始用SMA
    for price in closes[period:]:
        ema = (price - ema) * multiplier + ema
    return ema


def calc_rsi(closes, period=14):
    """RSI 相对强弱指标"""
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(-period, 0):
        change = closes[i] - closes[i - 1]
        gains.append(max(change, 0))
        losses.append(max(-change, 0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calc_bollinger(closes, period=20, std_dev=2):
    """布林带"""
    if len(closes) < period:
        return None, None, None
    sma = sum(closes[-period:]) / period
    variance = sum((c - sma) ** 2 for c in closes[-period:]) / period
    std = variance ** 0.5
    return sma + std_dev * std, sma, sma - std_dev * std


def calc_stoch(klines, k_period=14, d_period=3):
    """随机指标 Stochastic %K"""
    if len(klines) < k_period:
        return None
    highs = [float(k[2]) for k in klines[-k_period:]]
    lows = [float(k[3]) for k in klines[-k_period:]]
    close = float(klines[-1][4])
    highest = max(highs)
    lowest = min(lows)
    if highest == lowest:
        return 50
    return (close - lowest) / (highest - lowest) * 100


def analyze_coin(coin_key):
    """分析单个币种，返回关键位置数据"""
    cfg = COINS[coin_key]
    klines = fetch_klines(coin_key, 220)
    if not klines or not isinstance(klines, list):
        return None

    closes = [float(k[4]) for k in klines]
    highs = [float(k[2]) for k in klines]
    lows = [float(k[3]) for k in klines]
    price = closes[-1]

    # 均线
    sma10 = calc_sma(closes, 10)
    sma20 = calc_sma(closes, 20)
    sma50 = calc_sma(closes, 50)
    sma100 = calc_sma(closes, 100)
    sma200 = calc_sma(closes, 200)
    ema10 = calc_ema(closes, 10)
    ema20 = calc_ema(closes, 20)

    # 指标
    rsi = calc_rsi(closes, 14)
    stoch = calc_stoch(klines)
    bb_upper, bb_mid, bb_lower = calc_bollinger(closes, 20, 2)

    # 区间
    high_24h = max(highs[-1] for _ in [0])
    low_24h = min(lows[-1] for _ in [0])
    high_7d = max(highs[-7:])
    low_7d = min(lows[-7:])
    high_30d = max(highs[-30:])
    low_30d = min(lows[-30:])

    # 24h 变动
    change_24h = (closes[-1] / closes[-2] - 1) * 100 if len(closes) > 1 else 0

    return {
        "coin": coin_key,
        "name": cfg["name"],
        "decimals": cfg["decimals"],
        "price": price,
        "high_24h": highs[-1],
        "low_24h": lows[-1],
        "high_7d": high_7d,
        "low_7d": low_7d,
        "high_30d": high_30d,
        "low_30d": low_30d,
        "change_24h": change_24h,
        "sma10": sma10, "sma20": sma20, "sma50": sma50,
        "sma100": sma100, "sma200": sma200,
        "ema10": ema10, "ema20": ema20,
        "rsi": rsi, "stoch": stoch,
        "bb_upper": bb_upper, "bb_mid": bb_mid, "bb_lower": bb_lower,
    }


def build_coin_section(d):
    """构建单个币种的关键位置报告段"""
    fmt_str = f"{{:.{d['decimals']}f}}"
    price = d["price"]
    lines = [f"━━━ {d['name']} {d['coin']} · ${fmt_str.format(price)} ({d['change_24h']:+.1f}%) ━━━"]

    # 24h & 7d 区间
    lines.append(f"24h: ${fmt_str.format(d['low_24h'])} – ${fmt_str.format(d['high_24h'])} | "
                 f"7d: ${fmt_str.format(d['low_7d'])} – ${fmt_str.format(d['high_7d'])} | "
                 f"30d: ${fmt_str.format(d['low_30d'])} – ${fmt_str.format(d['high_30d'])}")

    # 收集所有关键价位
    levels = []
    for label, val, desc in [
        ("SMA200", d["sma200"], "长期牛熊线"),
        ("SMA100", d["sma100"], "中期均线"),
        ("SMA50", d["sma50"], "中期均线"),
        ("SMA20", d["sma20"], "短期防线"),
        ("SMA10", d["sma10"], "超短期"),
        ("30天高", d["high_30d"], "30天高点"),
        ("30天低", d["low_30d"], "30天低点"),
        ("7天低", d["low_7d"], "7天低点"),
        ("布林上轨", d["bb_upper"], "布林带上轨"),
        ("布林下轨", d["bb_lower"], "布林带下轨"),
    ]:
        if val:
            levels.append((label, val, desc))

    # 按价格排序，分阻力/支撑
    resistances = [(l, v, d) for l, v, d in levels if v > price * 1.005]
    supports = [(l, v, d) for l, v, d in levels if v < price * 0.995]
    resistances.sort(key=lambda x: -x[1])  # 从高到低
    supports.sort(key=lambda x: -x[1])     # 从高到低（近→远）

    # 阻力
    for i, (label, val, desc) in enumerate(resistances[:4]):
        tag = ["(近)", "(中)", "(中)", "(强)"][min(i, 3)]
        dist = (val / price - 1) * 100
        lines.append(f"  ▲ 阻力{tag}: ${fmt_str.format(val)} [{label} {desc}] +{dist:.1f}%")

    # 现价
    lines.append(f"  ━━━ 现价 ${fmt_str.format(price)} ━━━")

    # 支撑
    for i, (label, val, desc) in enumerate(supports[:4]):
        tag = ["(近)", "(中)", "(中)", "(强)"][min(i, 3)]
        dist = (price / val - 1) * 100
        lines.append(f"  ▼ 支撑{tag}: ${fmt_str.format(val)} [{label} {desc}] -{dist:.1f}%")

    # 指标
    ind_parts = []
    if d["rsi"]:
        tag = "超买" if d["rsi"] > 70 else "超卖" if d["rsi"] < 30 else "中性"
        ind_parts.append(f"RSI {d['rsi']:.0f}({tag})")
    if d["stoch"] is not None:
        tag = "超买" if d["stoch"] > 80 else "超卖" if d["stoch"] < 20 else "中性"
        ind_parts.append(f"Stoch {d['stoch']:.0f}({tag})")
    if ind_parts:
        lines.append(f"  指标: {' | '.join(ind_parts)}")

    # 趋势判断
    above_sma50 = d["sma50"] and price > d["sma50"]
    above_sma200 = d["sma200"] and price > d["sma200"]
    if above_sma200 and above_sma50:
        trend = "中期偏多（价在SMA50/200上方）"
    elif above_sma50 and not above_sma200:
        trend = "短期偏多中期偏弱（在SMA50上方但在SMA200下方）"
    elif not above_sma50 and above_sma200:
        trend = "短期回调中期偏多（在SMA50下方但在SMA200上方）"
    else:
        trend = "中期偏空（价在SMA50/200下方）"
    lines.append(f"  趋势: {trend}")

    # 操作建议
    advice = []
    if resistances:
        r1 = resistances[0][1]
        r_dist = (r1 / price - 1) * 100
        if r_dist < 2:
            advice.append(f"近阻力${fmt_str.format(r1)}: 放量突破→追多, 滞涨→减仓")
    if supports:
        s1 = supports[0][1]
        s_dist = (price / s1 - 1) * 100
        if s_dist < 2:
            advice.append(f"近支撑${fmt_str.format(s1)}: 企稳→做多, 跌破→止损")

    if not advice:
        if above_sma200 and above_sma50:
            advice.append("回调到支撑做多, 趋势偏多不逆势空")
        elif not above_sma50:
            advice.append("反弹到阻力减仓, 趋势偏弱不追高")
        else:
            advice.append("均线纠缠, 多看少动等方向")

    # 超买超卖提示
    if d["stoch"] is not None:
        if d["stoch"] < 20:
            advice.append("Stoch超卖: 短线反弹概率高")
        elif d["stoch"] > 80:
            advice.append("Stoch超买: 短线回调概率高")

    lines.append(f"  操作: {' | '.join(advice)}")
    return "\n".join(lines)


def get_push_label(now):
    """根据当前北京时间返回推送时段标签"""
    h = now.hour
    if h < 10:
        return "早盘"
    elif h < 14:
        return "午盘"
    else:
        return "晚盘"


def get_next_push_time(now):
    """返回下次推送时段"""
    h = now.hour
    if h < 8:
        return "12:00(午盘)"
    elif h < 14:
        return "18:00(晚盘)"
    else:
        return "次日07:00(早盘)"


def build_crypto_report():
    """构建完整 BTC+ETH 关键位置报告"""
    now = now_beijing()
    time_str = now.strftime("%m-%d %H:%M")
    push_label = get_push_label(now)

    lines = [f"═══════ 加密货币关键位置 | {time_str} | {push_label} ═══════\n"]

    for coin_key in ["BTC", "ETH"]:
        data = analyze_coin(coin_key)
        if not data:
            lines.append(f"━━━ {COINS[coin_key]['name']} {coin_key} ━━━\n⚠️ 数据获取失败\n")
            continue
        lines.append(build_coin_section(data))
        lines.append("")

    # 对比总结
    lines.append("━━━ 对比总结 ━━━")
    lines.append("• SMA200日线 = 长期牛熊分水岭: 站上=多头市场, 跌破=空头市场")
    lines.append("• SMA50日线 = 中期多空分界: 价在其上偏多, 在其下偏弱")
    lines.append("• Stoch <20 超卖反弹, >80 超买回调")
    lines.append("• 布林带上轨=短期阻力, 下轨=短期支撑")
    lines.append("• 阻力突破后变支撑, 支撑跌破后变阻力")
    lines.append("• 止损纪律 > 方向判断, 加密波动大务必设止损")
    lines.append("")
    lines.append(f"⏰ 下次推送: {get_next_push_time(now)} | 数据源: Binance")
    lines.append("⚠️ 技术面标注, 不构成投资建议")

    subject = f"【加密盯盘】{push_label} BTC+ETH关键位置 | {time_str}"
    body = "\n".join(lines)
    return subject, body


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


def main():
    now = now_beijing()
    print(f"[{now}] 加密盯盘启动 - BTC+ETH关键位置 ({get_push_label(now)})")

    subject, body = build_crypto_report()
    print(f"标题: {subject}")
    print(body[:800])

    try:
        send_email(subject, body)
        print("✅ 已发送")
    except Exception as e:
        print(f"❌ 发送失败: {e}")
        raise


if __name__ == "__main__":
    main()
