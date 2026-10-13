"""보유 종목 평가와 점검. 시세를 인자로 받는 순수 함수라 테스트하기 쉽다.

달러 종목과 원화 종목이 섞여 있으면 현재 원/달러 환율로 원화로 바꿔 합계와 비중을 낸다.
매수 당시 환율은 기록하지 않으므로 환율 변동에 따른 손익은 포함하지 않는다.
"""
from dataclasses import dataclass

from ..company.metrics import currency_of

# 점검 기준
STOCK_WEIGHT_LIMIT = 30.0  # 한 종목 비중(%)
SECTOR_WEIGHT_LIMIT = 50.0  # 한 업종 비중(%)
LOSS_LIMIT = -10.0  # 종목 수익률(%)
BAD_NEWS_MIN_IMPACT = 2


@dataclass
class Position:
    ticker: str
    name: str
    sector: str
    quantity: float
    avg_price: float
    price: float | None
    prev_close: float | None
    cost: float  # 종목 통화 기준
    currency: str = "KRW"
    value: float | None = None  # 종목 통화 기준
    pnl: float | None = None
    pnl_pct: float | None = None
    day_pct: float | None = None
    value_krw: float | None = None
    cost_krw: float | None = None
    weight: float | None = None  # 원화 환산 평가금액 기준 비중(%)


@dataclass
class Summary:
    """합계는 모두 원화 기준."""
    cost: float
    value: float
    pnl: float
    pnl_pct: float | None
    day_change: float
    day_pct: float | None
    missing_prices: list[str]
    fx: float | None = None  # 적용한 원/달러 환율
    value_usd: float | None = None  # 원화 합계를 달러로 환산


@dataclass
class Alert:
    level: str  # "warning" | "info"
    message: str


def evaluate(holdings, quotes: dict, fx: float | None = None) -> tuple[list[Position], Summary]:
    """quotes: {ticker: (현재가, 전일 종가)}, fx: 원/달러 환율.
    시세가 없거나 달러 종목인데 환율이 없으면 평가에서 빠진다."""
    positions = []
    for h in holdings:
        price, prev = quotes.get(h.ticker, (None, None))
        cur = currency_of(h.ticker)
        p = Position(h.ticker, h.name, h.sector, h.quantity, h.avg_price, price, prev, cost=h.cost, currency=cur)
        rate = 1.0 if cur == "KRW" else fx
        if price and rate:
            p.value = price * h.quantity
            p.pnl = p.value - p.cost
            p.pnl_pct = p.pnl / p.cost * 100
            if prev:
                p.day_pct = (price / prev - 1) * 100
            p.value_krw, p.cost_krw = p.value * rate, p.cost * rate
        positions.append(p)

    valued = [p for p in positions if p.value_krw is not None]
    total_value = sum(p.value_krw for p in valued)
    total_cost = sum(p.cost_krw for p in valued)
    for p in valued:
        p.weight = p.value_krw / total_value * 100 if total_value else None
    day_change = sum((p.price - p.prev_close) * p.quantity * (p.value_krw / p.value)
                     for p in valued if p.prev_close)
    prev_value = total_value - day_change
    summary = Summary(
        cost=total_cost,
        value=total_value,
        pnl=total_value - total_cost,
        pnl_pct=(total_value / total_cost - 1) * 100 if total_cost else None,
        day_change=day_change,
        day_pct=day_change / prev_value * 100 if prev_value else None,
        missing_prices=[p.name for p in positions if p.value_krw is None],
        fx=fx,
        value_usd=total_value / fx if fx else None,
    )
    return positions, summary


def sector_weights(positions) -> dict[str, float]:
    weights: dict[str, float] = {}
    for p in positions:
        if p.weight is not None:
            weights[p.sector] = weights.get(p.sector, 0) + p.weight
    return dict(sorted(weights.items(), key=lambda kv: kv[1], reverse=True))


def check(positions, news_by_name: dict | None = None) -> list[Alert]:
    """쏠림, 손실 구간, 보유 종목 악재 뉴스. news_by_name: {종목명: 기사 dict 목록}"""
    alerts = []
    valued = [p for p in positions if p.weight is not None]
    if len(valued) == 1:
        alerts.append(Alert("info", f"보유 종목이 {valued[0].name} 하나뿐이에요. 수익률이 이 종목에 그대로 따라가요."))
    elif len(valued) > 1:
        for p in valued:
            if p.weight >= STOCK_WEIGHT_LIMIT:
                alerts.append(Alert("warning", f"{p.name} 비중이 {p.weight:.0f}%예요. 한 종목이 {STOCK_WEIGHT_LIMIT:.0f}% 이상이면 그 종목 하나에 수익률이 크게 좌우돼요."))
        for sector, w in sector_weights(valued).items():
            if w >= SECTOR_WEIGHT_LIMIT:
                alerts.append(Alert("warning", f"{sector} 업종 비중이 {w:.0f}%예요. 같은 업종은 함께 오르내리는 경향이 있어요."))
    for p in positions:
        if p.pnl_pct is not None and p.pnl_pct <= LOSS_LIMIT:
            alerts.append(Alert("info", f"{p.name}이(가) 평균단가 대비 {p.pnl_pct:.1f}%예요. 처음 매수한 이유가 아직 유효한지 점검해 보세요."))
    for name, articles in (news_by_name or {}).items():
        bad = [a for a in articles if a.get("sentiment") == "악재" and (a.get("impact") or 0) >= BAD_NEWS_MIN_IMPACT]
        if bad:
            top = max(bad, key=lambda a: a["impact"])
            more = f" 외 {len(bad) - 1}건" if len(bad) > 1 else ""
            alerts.append(Alert("warning", f"{name} 악재 뉴스: {top['title']}{more}"))
    return alerts
