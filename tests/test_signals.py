import json
import math
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from daejini.news.analyze import AnalysisError
from daejini.signals.analyze import build_prompt, explain
from daejini.signals.backtest import STRATEGIES, buy_and_hold, run, simulate, support_zone
from daejini.signals.indicators import add_indicators, current_signals, pivots, zones


def frame(closes, spread=1.0):
    closes = np.asarray(closes, dtype=float)
    return pd.DataFrame({
        "date": pd.bdate_range("2024-01-01", periods=len(closes)),
        "open": closes, "high": closes + spread, "low": closes - spread, "close": closes,
        "volume": 1000,
    })


def wave(n=400, seed=0):
    """사인파 + 잡음: 오르내림이 반복되는 가상 주가."""
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    return frame(100 + 10 * np.sin(t / 15) + rng.normal(0, 0.8, n))


# 지표
def test_rsi_extremes_and_flat_bollinger():
    up = add_indicators(frame(np.arange(1, 61)))
    assert up["rsi"].iloc[-1] == pytest.approx(100)
    down = add_indicators(frame(np.arange(60, 0, -1)))
    assert down["rsi"].iloc[-1] == pytest.approx(0, abs=1e-6)
    flat = add_indicators(frame([50] * 40))
    assert flat["bb_upper"].iloc[-1] == flat["bb_lower"].iloc[-1] == 50
    assert flat["atr"].iloc[-1] == pytest.approx(2.0)  # 고가-저가 = 2


def test_pivots_find_v_bottom_and_peak():
    df = frame([10, 9, 8, 7, 6, 5, 6, 7, 8, 9, 10, 11, 12, 11, 10, 9, 8, 7], spread=0)
    lows, highs = pivots(df, window=3)
    assert lows == [5.0] and highs == [12.0]


def test_zones_pick_nearest_levels_around_price():
    df = add_indicators(wave())
    z = zones(df)
    assert z.support < z.price < z.resistance
    assert z.buy_zone[0] < z.support < z.buy_zone[1]
    assert z.stop == pytest.approx(z.support - 1.5 * z.atr)


def test_zones_without_support_on_new_low():
    df = add_indicators(frame(np.linspace(200, 100, 200)))
    z = zones(df)
    assert z.support is None and z.buy_zone is None and z.stop is None


def test_current_signals_trend_states():
    names = {s.name: s.state for s in current_signals(add_indicators(frame(np.linspace(100, 200, 200))))}
    assert names["추세"] == "정배열" and "과매수" in names["RSI"]
    names = {s.name: s.state for s in current_signals(add_indicators(frame(np.linspace(200, 100, 200))))}
    assert names["추세"] == "역배열" and "과매도" in names["RSI"]


# 시뮬레이션
def test_simulate_executes_next_open_with_costs():
    df = pd.DataFrame({
        "date": pd.bdate_range("2024-01-01", periods=4),
        "open": [100.0, 100.0, 110.0, 120.0], "close": [100.0, 105.0, 115.0, 120.0],
        "high": 0, "low": 0,
    })
    target = pd.Series([1, 1, 0, 0])  # 0일 종가에 매수 결정 → 1일 시가 100에 매수, 2일 종가에 매도 결정 → 3일 시가 120
    r = simulate(df, target, fee_pct=0.1, tax_pct=0.2)
    expected = (1 - 0.001) / 100 * 120 * (1 - 0.001 - 0.002)
    assert r.equity.iloc[-1] == pytest.approx(expected)
    [t] = r.trades
    assert t["매수가"] == 100 and t["매도가"] == 120 and t["상태"] == "청산"
    assert r.win_rate == 100 and r.exposure == pytest.approx(200 / 3)


def test_buy_and_hold_and_drawdown():
    df = frame([100, 100, 50, 80, 120])
    r = buy_and_hold(df, fee_pct=0, tax_pct=0)
    assert r.total_return == pytest.approx(20)
    assert r.mdd == pytest.approx(-50)
    assert r.trades[0]["상태"] == "보유 중(평가)"


@pytest.mark.parametrize("key", list(STRATEGIES))
def test_strategies_never_use_future_data(key):
    """앞부분 신호는 뒤에 데이터가 더 붙어도 바뀌지 않아야 한다."""
    df = add_indicators(wave(400))
    fn = STRATEGIES[key][2]
    full = fn(df)
    head = fn(add_indicators(wave(400).iloc[:300]))
    assert full.iloc[:300].tolist() == head.tolist()


def test_run_starts_at_start_date_and_compares_with_hold():
    df = add_indicators(wave(400))
    start = df["date"].iloc[200]
    r, hold = run(df, "bollinger", start, fee_pct=0, tax_pct=0)
    assert r.equity.index[0] == start and hold.equity.index[0] == start
    assert len(r.trades) > 0 and math.isfinite(r.total_return)


# AI 해설
class FakeClient:
    def __init__(self, text, stop_reason="end_turn"):
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: SimpleNamespace(
            stop_reason=stop_reason, content=[SimpleNamespace(type="text", text=text)])))


def test_explain_prompt_and_parse():
    df = add_indicators(wave())
    sig, z = current_signals(df), zones(df)
    r, hold = run(df, "ma_cross", df["date"].iloc[200])
    prompt = build_prompt("테스트", sig, z, {"이동평균 교차": r, "단순 보유": hold}, 3)
    assert "최근 3년 백테스트" in prompt and "이동평균 교차: 총수익률" in prompt and "지지선" in prompt
    ok = json.dumps({"summary": "s", "points": ["p"], "backtest": "b", "caution": "c"})
    assert explain(FakeClient(ok), "테스트", sig, z, {}, 3).summary == "s"
    with pytest.raises(AnalysisError):
        explain(FakeClient(ok, "refusal"), "테스트", sig, z, {}, 3)


def test_zones_never_overlap_when_levels_are_close():
    from daejini.signals.indicators import Zones
    df = add_indicators(wave(seed=3))
    for end in range(200, 400, 7):
        z = zones(df.iloc[:end])
        if z and z.buy_zone and z.sell_zone:
            assert z.buy_zone[1] <= z.sell_zone[0]
            assert z.buy_zone[0] < z.support < z.buy_zone[1] and z.sell_zone[0] < z.resistance < z.sell_zone[1]
