"""여러 화면이 함께 쓰는 Streamlit 도우미 (캐시된 저장소·클라이언트·데이터)."""
from datetime import datetime, timedelta, timezone

import streamlit as st

from .company import data as company_data
from .company.metrics import METRIC_INFO, median
from .news.service import make_client
from .news.store import Store

KST = timezone(timedelta(hours=9))
MD_SPECIAL = set("\\`*_[]<>$#|~:")


@st.cache_resource
def get_store():
    return Store()


@st.cache_resource
def get_client():
    return make_client()


def md(text: str) -> str:
    """외부 텍스트(기사 제목 등)가 마크다운으로 해석되지 않게 이스케이프."""
    return "".join("\\" + c if c in MD_SPECIAL else c for c in text or "")


def dollars(text: str) -> str:
    """마크다운에서 $...$ 사이가 수식으로 바뀌지 않게 $ 기호를 이스케이프."""
    return text.replace("$", r"\$")


def kst(iso: str) -> str:
    if not iso:
        return ""
    t = datetime.fromisoformat(iso).astimezone(KST)
    return f"{t.month}월 {t.day}일 {t:%H:%M}"


@st.cache_resource
def get_portfolio():
    from .portfolio.store import PortfolioStore

    return PortfolioStore()


@st.cache_data(ttl=600, show_spinner=False)
def quote(ticker: str):
    """(현재가, 전일 종가). 10분 캐시."""
    return company_data.fetch_quote(ticker)


@st.cache_data(ttl=600, show_spinner=False)
def lookup(ticker: str):
    """종목 이름·현재가·통화 확인. 10분 캐시."""
    return company_data.lookup(ticker)


@st.cache_data(ttl=600, show_spinner=False)
def usd_krw() -> float | None:
    """원/달러 환율. 10분 캐시."""
    try:
        return company_data.fetch_quote("KRW=X")[0]
    except Exception:
        return None


@st.cache_data(ttl=600, show_spinner=False)
def board(tickers: tuple[str, ...]):
    """메인 화면 시세판. 10분 캐시."""
    return company_data.fetch_board(list(tickers))


@st.cache_data(ttl=1800, show_spinner=False)
def refresh_market_news():
    """시장 뉴스 수집·요약. 30분에 한 번만 실제로 실행되고,
    기사 목록이 그대로면 AI 요약도 다시 하지 않는다."""
    from .news.market import refresh_market

    return refresh_market(get_store(), get_client())


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def snapshot(name: str):
    ticker, sector = company_data.company_index()[name]
    return company_data.fetch_snapshot(name, ticker, sector)


@st.cache_data(ttl=3600, show_spinner=False)
def history(ticker: str):
    return company_data.fetch_history(ticker, period="2y")


@st.cache_data(ttl=3600, show_spinner=False)
def ohlc_with_indicators(ticker: str):
    from .signals.indicators import add_indicators

    return add_indicators(company_data.fetch_ohlc(ticker, "5y"))


def sector_snapshots(sector: str):
    names = list(company_data.load_companies()[sector])
    return [snapshot(n) for n in names]


def sector_average(snaps) -> dict:
    """업종 기준값: 기업들의 중간값."""
    return {key: median(getattr(s.metrics, key) for s in snaps if not s.error) for key in METRIC_INFO}
