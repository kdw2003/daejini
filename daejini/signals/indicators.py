"""기술적 지표와 지지·저항 구간. 입력은 date, open, high, low, close 열을 가진 DataFrame."""
from dataclasses import dataclass

import pandas as pd


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    close = df["close"]
    for n in (20, 60, 120):
        df[f"ma{n}"] = close.rolling(n).mean()

    # RSI(14), 와일더 방식
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    df["rsi"] = 100 - 100 / (1 + gain / loss)
    df.loc[loss == 0, "rsi"] = 100.0

    # 볼린저 밴드(20일, 2표준편차)
    std = close.rolling(20).std()
    df["bb_mid"] = df["ma20"]
    df["bb_upper"] = df["ma20"] + 2 * std
    df["bb_lower"] = df["ma20"] - 2 * std

    # MACD(12, 26, 9)
    macd = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
    df["macd"] = macd
    df["macd_signal"] = macd.ewm(span=9, adjust=False).mean()

    # ATR(14): 하루 평균 변동폭
    prev_close = close.shift()
    true_range = pd.concat(
        [df["high"] - df["low"], (df["high"] - prev_close).abs(), (df["low"] - prev_close).abs()], axis=1
    ).max(axis=1)
    df["atr"] = true_range.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    return df


def pivots(df: pd.DataFrame, window: int = 5) -> tuple[list[float], list[float]]:
    """앞뒤 window일 중 가장 낮은 저가(저점)와 가장 높은 고가(고점)."""
    lows, highs = [], []
    low, high = df["low"].to_numpy(), df["high"].to_numpy()
    for i in range(window, len(df) - window):
        seg_low, seg_high = low[i - window: i + window + 1], high[i - window: i + window + 1]
        if low[i] == seg_low.min():
            lows.append(float(low[i]))
        if high[i] == seg_high.max():
            highs.append(float(high[i]))
    return lows, highs


@dataclass
class Zones:
    price: float
    atr: float
    support: float | None  # 현재가 아래 가장 가까운 지지선
    resistance: float | None  # 현재가 위 가장 가까운 저항선
    buy_zone: tuple[float, float] | None  # 관심 구간 (지지선 ± 0.5 ATR)
    sell_zone: tuple[float, float] | None  # 경계 구간 (저항선 ± 0.5 ATR)
    stop: float | None  # 손절 참고선 (지지선 - 1.5 ATR)


def zones(df: pd.DataFrame, lookback: int = 120, window: int = 5) -> Zones | None:
    """최근 lookback일의 저점·고점에서 현재가에 가장 가까운 지지·저항을 고른다.

    df에는 add_indicators로 atr이 있어야 한다. 백테스트에서도 같은 함수를
    그날까지의 데이터에만 적용하므로 미래 정보가 섞이지 않는다.
    """
    if len(df) < max(lookback, 30) or pd.isna(df["atr"].iloc[-1]):
        return None
    recent = df.iloc[-lookback:]
    price, atr = float(df["close"].iloc[-1]), float(df["atr"].iloc[-1])
    lows, highs = pivots(recent, window)
    # 최근 고점이 무너지면 지지 역할로, 저점을 뚫으면 저항 역할로 바뀌므로 둘 다 후보로 본다
    levels = lows + highs
    below = [x for x in levels if x < price - 0.25 * atr]
    above = [x for x in levels if x > price + 0.25 * atr]
    support = max(below) if below else None
    resistance = min(above) if above else None
    half = 0.5 * atr
    buy_zone = (support - half, support + half) if support else None
    sell_zone = (resistance - half, resistance + half) if resistance else None
    # 지지·저항이 가까워 두 구간이 겹치면 중간 가격에서 나눈다
    if buy_zone and sell_zone and buy_zone[1] > sell_zone[0]:
        mid = (support + resistance) / 2
        buy_zone, sell_zone = (buy_zone[0], mid), (mid, sell_zone[1])
    return Zones(
        price=price,
        atr=atr,
        support=support,
        resistance=resistance,
        buy_zone=buy_zone,
        sell_zone=sell_zone,
        stop=support - 1.5 * atr if support else None,
    )


@dataclass
class Signal:
    name: str
    state: str  # 화면에 보일 상태
    tone: str  # "up" | "down" | "neutral"
    detail: str


def current_signals(df: pd.DataFrame) -> list[Signal]:
    """마지막 날 기준 지표 상태를 쉬운 말로."""
    last, prev = df.iloc[-1], df.iloc[-2]
    out = []

    if pd.notna(last["ma120"]):
        if last["ma20"] > last["ma60"] > last["ma120"]:
            out.append(Signal("추세", "정배열", "up", "20일 > 60일 > 120일 이동평균. 단기·중기·장기 흐름이 모두 위를 향해요."))
        elif last["ma20"] < last["ma60"] < last["ma120"]:
            out.append(Signal("추세", "역배열", "down", "20일 < 60일 < 120일 이동평균. 흐름이 모두 아래를 향해요."))
        else:
            out.append(Signal("추세", "혼조", "neutral", "이동평균이 섞여 있어 뚜렷한 방향이 없어요."))

    rsi = last["rsi"]
    if pd.notna(rsi):
        if rsi >= 70:
            out.append(Signal("RSI", f"{rsi:.0f} 과매수", "up", "70 이상이면 짧은 기간에 많이 올라 숨 고르기가 나올 수 있어요."))
        elif rsi <= 30:
            out.append(Signal("RSI", f"{rsi:.0f} 과매도", "down", "30 이하이면 짧은 기간에 많이 내려 반등이 나올 수 있어요."))
        else:
            out.append(Signal("RSI", f"{rsi:.0f} 보통", "neutral", "30~70 사이로 과열도 침체도 아니에요."))

    if pd.notna(last["bb_upper"]):
        if last["close"] > last["bb_upper"]:
            out.append(Signal("볼린저 밴드", "상단 돌파", "up", "주가가 20일 평균에서 2표준편차 넘게 위에 있어요. 강한 상승이거나 과열이에요."))
        elif last["close"] < last["bb_lower"]:
            out.append(Signal("볼린저 밴드", "하단 이탈", "down", "주가가 20일 평균에서 2표준편차 넘게 아래에 있어요. 급락이거나 과매도예요."))
        else:
            pos = (last["close"] - last["bb_lower"]) / (last["bb_upper"] - last["bb_lower"]) * 100
            out.append(Signal("볼린저 밴드", f"밴드 안 {pos:.0f}%", "neutral", "0%는 하단, 100%는 상단이에요."))

    crossed_up = prev["macd"] <= prev["macd_signal"] and last["macd"] > last["macd_signal"]
    crossed_down = prev["macd"] >= prev["macd_signal"] and last["macd"] < last["macd_signal"]
    if crossed_up:
        out.append(Signal("MACD", "골든크로스", "up", "MACD가 신호선을 위로 뚫었어요. 상승 탄력이 붙는 신호로 봐요."))
    elif crossed_down:
        out.append(Signal("MACD", "데드크로스", "down", "MACD가 신호선을 아래로 뚫었어요. 하락 탄력이 붙는 신호로 봐요."))
    else:
        above = last["macd"] > last["macd_signal"]
        out.append(Signal("MACD", "신호선 위" if above else "신호선 아래", "up" if above else "down",
                          "MACD가 신호선 위면 상승 탄력, 아래면 하락 탄력이 우세해요."))
    return out
