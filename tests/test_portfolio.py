import pytest

from daejini.portfolio.store import Holding, PortfolioStore
from daejini.portfolio.valuation import check, evaluate, sector_weights


def test_buy_merges_average_price_and_update_remove():
    s = PortfolioStore(":memory:")
    s.buy("005930.KS", "삼성전자", "반도체", 10, 200_000)
    h = s.buy("005930.KS", "삼성전자", "반도체", 10, 250_000)  # 추가 매수
    assert h.quantity == 20 and h.avg_price == pytest.approx(225_000)
    s.update("005930.KS", 5, 210_000)
    assert s.holdings()[0].cost == pytest.approx(1_050_000)
    with pytest.raises(ValueError):
        s.buy("000660.KS", "SK하이닉스", "반도체", 0, 100)
    s.remove("005930.KS")
    assert s.holdings() == []


HOLDINGS = [
    Holding("A", "에이", "반도체", 10, 100.0),  # 원금 1,000
    Holding("B", "비", "반도체", 10, 300.0),  # 원금 3,000
    Holding("C", "씨", "금융", 10, 100.0),  # 원금 1,000
]
QUOTES = {"A": (120.0, 100.0), "B": (240.0, 250.0), "C": (100.0, None)}


def test_evaluate_positions_and_summary():
    positions, s = evaluate(HOLDINGS, QUOTES, fx=1.0)
    a, b, c = positions
    assert a.value == 1200 and a.pnl == 200 and a.pnl_pct == pytest.approx(20) and a.day_pct == pytest.approx(20)
    assert b.pnl_pct == pytest.approx(-20) and c.day_pct is None
    assert s.value == 4600 and s.cost == 5000 and s.pnl == -400 and s.pnl_pct == pytest.approx(-8)
    assert s.day_change == pytest.approx(200 - 100)  # A +20×10, B -10×10, C 전일가 없음
    assert sum(p.weight for p in positions) == pytest.approx(100)
    assert sector_weights(positions) == pytest.approx({"반도체": 3600 / 4600 * 100, "금융": 1000 / 4600 * 100})


def test_evaluate_skips_missing_quotes():
    positions, s = evaluate(HOLDINGS, {"A": (120.0, 100.0)}, fx=1.0)
    assert s.missing_prices == ["비", "씨"] and positions[0].weight == pytest.approx(100)


def test_check_concentration_loss_and_bad_news():
    positions, _ = evaluate(HOLDINGS, QUOTES, fx=1.0)
    news = {"에이": [{"title": "대규모 리콜", "sentiment": "악재", "impact": 3},
                    {"title": "소송 제기", "sentiment": "악재", "impact": 2},
                    {"title": "작은 악재", "sentiment": "악재", "impact": 1}],
            "씨": [{"title": "배당 확대", "sentiment": "호재", "impact": 3}]}
    messages = [a.message for a in check(positions, news)]
    assert any("비 비중이 52%" in m for m in messages)
    assert any("반도체 업종 비중이 78%" in m for m in messages)
    assert any("비이(가) 평균단가 대비 -20.0%" in m for m in messages)
    assert any("에이 악재 뉴스: 대규모 리콜 외 1건" in m for m in messages)
    assert not any("씨" in m for m in messages)


def test_check_single_holding_and_quiet_portfolio():
    positions, _ = evaluate(HOLDINGS[:1], QUOTES, fx=1.0)
    [alert] = check(positions)
    assert "하나뿐" in alert.message and alert.level == "info"
    even = [Holding(t, t, sec, 10, 100.0) for t, sec in (("A", "가"), ("B", "나"), ("C", "다"), ("D", "라"))]
    positions, _ = evaluate(even, {t: (100.0, 100.0) for t in "ABCD"}, fx=1.0)
    assert check(positions) == []


def test_mixed_currency_converted_to_krw():
    holdings = [Holding("NVDA", "엔비디아", "반도체", 10, 100.0),  # 원금 $1,000
                Holding("005930.KS", "삼성전자", "반도체", 10, 100_000.0)]  # 원금 1,000,000원
    quotes = {"NVDA": (120.0, 110.0), "005930.KS": (90_000.0, 100_000.0)}
    positions, s = evaluate(holdings, quotes, fx=1400.0)
    nvda, sam = positions
    assert nvda.currency == "USD" and nvda.value == 1200 and nvda.value_krw == 1_680_000
    assert sam.currency == "KRW" and sam.value_krw == 900_000
    assert s.value == 2_580_000 and s.cost == 1_400_000 + 1_000_000
    assert s.day_change == pytest.approx(10 * 10 * 1400 - 10_000 * 10)
    assert s.value_usd == pytest.approx(2_580_000 / 1400)
    assert nvda.weight == pytest.approx(1_680_000 / 2_580_000 * 100)


def test_usd_holding_without_fx_is_left_out():
    positions, s = evaluate([Holding("NVDA", "엔비디아", "반도체", 1, 100.0)], {"NVDA": (120.0, 110.0)}, fx=None)
    assert s.missing_prices == ["엔비디아"] and positions[0].weight is None
