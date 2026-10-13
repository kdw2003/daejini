"""재무제표와 시가총액으로 핵심 지표를 계산한다.

yfinance가 주는 PER·PBR은 한국 종목에서 비어 있는 경우가 많아,
모든 기업을 같은 기준(현재 시가총액 ÷ 최근 회계연도 실적)으로 직접 계산한다.
"""
from dataclasses import dataclass, field


@dataclass
class Annual:
    year: int
    revenue: float | None = None
    operating_income: float | None = None
    net_income: float | None = None  # 지배주주 순이익
    equity: float | None = None  # 지배주주 자기자본
    liabilities: float | None = None


@dataclass
class Metrics:
    per: float | None = None
    pbr: float | None = None
    roe: float | None = None
    operating_margin: float | None = None
    debt_ratio: float | None = None
    revenue_growth: float | None = None
    loss: bool = False  # 순손실이면 PER 대신 '적자'


# 지표 이름, 단위, 높을수록 좋은지, 정의
METRIC_INFO = {
    "per": ("PER", "배", False, "주가수익비율. 시가총액 ÷ 순이익. 낮을수록 이익 대비 싸게 거래돼요."),
    "pbr": ("PBR", "배", False, "주가순자산비율. 시가총액 ÷ 자기자본. 1보다 낮으면 장부가보다 싸게 거래돼요."),
    "roe": ("ROE", "%", True, "자기자본이익률. 순이익 ÷ 자기자본. 높을수록 주주 돈으로 이익을 잘 내요."),
    "operating_margin": ("영업이익률", "%", True, "영업이익 ÷ 매출. 본업에서 남기는 비율이에요. 금융사는 계산하지 않아요."),
    "debt_ratio": ("부채비율", "%", False, "부채총계 ÷ 자기자본. 높을수록 빚이 많아요. 금융사는 구조상 높게 나와요."),
    "revenue_growth": ("매출성장률", "%", True, "직전 회계연도 대비 매출 증가율이에요."),
}


def _ratio(a, b):
    if a is None or b is None or b == 0:
        return None
    return a / b


def compute(annuals: list[Annual], market_cap: float | None) -> Metrics:
    """annuals: 최신 연도가 먼저 오도록 정렬된 연간 실적."""
    if not annuals:
        return Metrics()
    cur = annuals[0]
    prev = annuals[1] if len(annuals) > 1 else None
    m = Metrics()

    if cur.net_income is not None and cur.net_income <= 0:
        m.loss = True
    else:
        m.per = _ratio(market_cap, cur.net_income)
    if cur.equity and cur.equity > 0:
        m.pbr = _ratio(market_cap, cur.equity)
        m.roe = _pct(_ratio(cur.net_income, cur.equity))
        m.debt_ratio = _pct(_ratio(cur.liabilities, cur.equity))
    m.operating_margin = _pct(_ratio(cur.operating_income, cur.revenue))
    if prev and prev.revenue and prev.revenue > 0 and cur.revenue is not None:
        m.revenue_growth = _pct(cur.revenue / prev.revenue - 1)
    return m


def _pct(x):
    return None if x is None else x * 100


def average(values) -> float | None:
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None


def median(values) -> float | None:
    """중간값. 한 기업의 극단값(예: 자사주 매입으로 자기자본이 작아진 기업의 ROE)에 덜 흔들린다."""
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    mid = len(vals) // 2
    return vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2


def fmt_metric(key: str, value, loss: bool = False) -> str:
    if key == "per" and loss:
        return "적자"
    if value is None:
        return "—"
    unit = METRIC_INFO[key][1]
    return f"{value:,.1f}{unit}"


def currency_of(ticker: str) -> str:
    """한국 종목(.KS/.KQ)은 원화, 나머지는 달러."""
    return "KRW" if ticker.upper().endswith((".KS", ".KQ")) else "USD"


def fmt_money(value, currency: str = "KRW") -> str:
    """큰 금액: 원화는 조·억 원, 달러는 조·억 달러 또는 $."""
    if currency == "KRW":
        return fmt_krw(value)
    if value is None:
        return "—"
    sign = "-" if value < 0 else ""
    v = abs(value)
    if v >= 1e12:
        return f"{sign}{v / 1e12:,.2f}조 달러"
    if v >= 1e8:
        return f"{sign}{v / 1e8:,.0f}억 달러"
    if v >= 1e4:
        return f"{sign}${v:,.0f}"
    return f"{sign}${v:,.2f}"


def fmt_price(value, currency: str = "KRW") -> str:
    """주가: 원화는 원 단위 정수, 달러는 센트까지."""
    if value is None:
        return "—"
    return f"{value:,.0f}원" if currency == "KRW" else f"${value:,.2f}"


def fmt_krw(value) -> str:
    """원 단위 금액을 조·억 단위로."""
    if value is None:
        return "—"
    sign = "-" if value < 0 else ""
    v = abs(value)
    if v >= 1e12:
        return f"{sign}{v / 1e12:,.1f}조 원"
    if v >= 1e8:
        return f"{sign}{v / 1e8:,.0f}억 원"
    return f"{sign}{v:,.0f}원"


@dataclass
class Snapshot:
    name: str
    ticker: str
    sector: str
    currency: str = "KRW"
    price: float | None = None
    market_cap: float | None = None
    year_high: float | None = None
    year_low: float | None = None
    annuals: list[Annual] = field(default_factory=list)
    metrics: Metrics = field(default_factory=Metrics)
    error: str = ""
