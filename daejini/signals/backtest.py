"""전략 백테스트. 신호는 그날 종가까지의 데이터로만 정하고, 거래는 다음 날 시가에 한다.

- 매수만 하는 전략(공매도 없음), 신호가 나면 전액 매수·전액 매도
- 비용: 매수·매도 수수료, 매도 시 증권거래세. 슬리피지(호가 차이)는 반영하지 않는다.
"""
from dataclasses import dataclass, field

import pandas as pd

from .indicators import zones

DEFAULT_FEE_PCT = 0.015  # 증권사 수수료(%), 매수·매도 각각
DEFAULT_TAX_PCT = 0.20  # 증권거래세(%), 매도 시


# 전략: df(지표 포함) → 그날 종가 기준 목표 보유 여부(0/1) Series
def ma_cross(df):
    return (df["ma20"] > df["ma60"]).astype(int).where(df["ma60"].notna(), 0)


def rsi_reversal(df):
    pos, holding = [], 0
    for rsi in df["rsi"]:
        if not holding and rsi <= 30:
            holding = 1
        elif holding and rsi >= 70:
            holding = 0
        pos.append(holding)
    return pd.Series(pos, index=df.index)


def bollinger_reversal(df):
    pos, holding = [], 0
    for close, lower, mid in zip(df["close"], df["bb_lower"], df["bb_mid"]):
        if not holding and pd.notna(lower) and close < lower:
            holding = 1
        elif holding and close > mid:
            holding = 0
        pos.append(holding)
    return pd.Series(pos, index=df.index)


def support_zone(df, lookback: int = 120):
    """관심 구간(지지선 근처)에 들어오면 매수, 저항 구간 도달이나 손절선 이탈 시 매도.

    매일 그날까지의 데이터로만 지지·저항을 다시 계산한다.
    """
    pos, holding, stop, target = [], 0, None, None
    closes = df["close"].to_numpy()
    for i in range(len(df)):
        close = closes[i]
        if holding:
            if close <= stop or close >= target:
                holding = 0
        else:
            z = zones(df.iloc[: i + 1], lookback=lookback) if i + 1 >= lookback else None
            if z and z.buy_zone and z.buy_zone[0] <= close <= z.buy_zone[1]:
                holding = 1
                stop = z.stop
                target = z.sell_zone[0] if z.sell_zone else close + 3 * z.atr
        pos.append(holding)
    return pd.Series(pos, index=df.index)


STRATEGIES = {
    "ma_cross": ("이동평균 교차", "20일 이동평균이 60일 위에 있으면 보유, 아래로 내려가면 매도", ma_cross),
    "rsi": ("RSI 역추세", "RSI 30 이하에서 매수, 70 이상에서 매도", rsi_reversal),
    "bollinger": ("볼린저 반등", "종가가 볼린저 하단 아래면 매수, 중심선(20일 평균) 위로 오면 매도", bollinger_reversal),
    "zone": ("지지 구간 매수", "이 화면의 관심 구간에서 매수, 경계 구간 도달이나 손절 참고선 이탈 시 매도", support_zone),
}


@dataclass
class Result:
    equity: pd.Series  # 날짜별 자산 (시작 1.0)
    trades: list[dict] = field(default_factory=list)
    total_return: float = 0.0  # %
    cagr: float | None = None  # %
    mdd: float = 0.0  # 최대 낙폭 %, 음수
    win_rate: float | None = None  # %
    avg_days: float | None = None
    exposure: float = 0.0  # 보유 기간 비율 %


def simulate(df, target, fee_pct=DEFAULT_FEE_PCT, tax_pct=DEFAULT_TAX_PCT) -> Result:
    """target[i]는 i일 종가 기준 결정, i+1일 시가에 실행."""
    fee, tax = fee_pct / 100, tax_pct / 100
    dates, opens, closes = df["date"].to_list(), df["open"].to_numpy(), df["close"].to_numpy()
    target = target.to_numpy()
    cash, shares, entry = 1.0, 0.0, None
    equity, trades, held_days = [1.0], [], 0

    for i in range(1, len(df)):
        want = target[i - 1]
        if want and shares == 0:
            shares = cash * (1 - fee) / opens[i]
            entry = (dates[i], opens[i], cash)
            cash = 0.0
        elif not want and shares > 0:
            cash = shares * opens[i] * (1 - fee - tax)
            trades.append(_trade(entry, dates[i], opens[i], cash))
            shares = 0.0
        if shares > 0:
            held_days += 1
        equity.append(cash + shares * closes[i])

    # 마지막 날 보유 중이면 매도 비용을 뺀 청산 가치로 평가
    if shares > 0:
        final = shares * closes[-1] * (1 - fee - tax)
        trades.append(_trade(entry, dates[-1], closes[-1], final, still_open=True))
        equity[-1] = final
    return _stats(pd.Series(equity, index=pd.DatetimeIndex(dates)), trades, held_days)


def buy_and_hold(df, fee_pct=DEFAULT_FEE_PCT, tax_pct=DEFAULT_TAX_PCT) -> Result:
    target = pd.Series(1, index=df.index)
    return simulate(df, target, fee_pct, tax_pct)


def _trade(entry, exit_date, exit_price, exit_value, still_open=False):
    entry_date, entry_price, entry_value = entry
    return {
        "매수일": entry_date, "매수가": entry_price, "매도일": exit_date, "매도가": exit_price,
        "수익률(%)": (exit_value / entry_value - 1) * 100,
        "보유일": (exit_date - entry_date).days,
        "상태": "보유 중(평가)" if still_open else "청산",
    }


def _stats(equity: pd.Series, trades, held_days) -> Result:
    r = Result(equity=equity, trades=trades)
    r.total_return = (equity.iloc[-1] - 1) * 100
    years = (equity.index[-1] - equity.index[0]).days / 365.25
    if years > 0 and equity.iloc[-1] > 0:
        r.cagr = (equity.iloc[-1] ** (1 / years) - 1) * 100
    r.mdd = float((equity / equity.cummax() - 1).min() * 100)
    if trades:
        r.win_rate = sum(t["수익률(%)"] > 0 for t in trades) / len(trades) * 100
        r.avg_days = sum(t["보유일"] for t in trades) / len(trades)
    r.exposure = held_days / max(len(equity) - 1, 1) * 100
    return r


def run(df_with_indicators, strategy: str, start, fee_pct=DEFAULT_FEE_PCT, tax_pct=DEFAULT_TAX_PCT):
    """지표는 시작일 이전 데이터로 미리 계산해 두고(워밍업), 시작일부터 거래한다."""
    target = STRATEGIES[strategy][2](df_with_indicators)
    mask = df_with_indicators["date"] >= pd.Timestamp(start)
    window = df_with_indicators[mask].reset_index(drop=True)
    return simulate(window, target[mask].reset_index(drop=True), fee_pct, tax_pct), buy_and_hold(window, fee_pct, tax_pct)
