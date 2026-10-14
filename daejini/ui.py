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
def _cached_client():
    return make_client()


def get_client():
    """Claude 클라이언트. 키가 없어서 None이면 기억하지 않아, 나중에 키를 넣으면 바로 쓰인다."""
    client = _cached_client()
    if client is None:
        _cached_client.clear()
    return client


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


def refresh_market_news():
    """시장 뉴스 수집·요약. 30분에 한 번만 실제로 실행되고, 기사 목록이 그대로면 AI 요약도 다시 하지 않는다.
    API 키가 새로 생기면 바로 요약하도록 키 유무를 캐시 구분값으로 쓴다."""
    return _refresh_market_news(get_client() is not None)


@st.cache_data(ttl=1800, show_spinner=False)
def _refresh_market_news(has_client: bool):
    from .news.market import refresh_market

    return refresh_market(get_store(), get_client())


NEWS_REFRESH_SECONDS = 1800


@st.cache_resource
def _news_fetched_at() -> dict:
    """{(키워드, 기간): 마지막으로 수집에 성공한 시각}. 모든 접속자가 함께 쓴다."""
    return {}


def refresh_keyword_news(keyword: str, days: int, force: bool = False):
    """키워드 뉴스 수집·분석. 성공한 뒤 30분 안에는 다시 모으지 않는다(None 반환).
    실패는 기억하지 않아서 다음에 열 때 바로 다시 시도한다."""
    import time

    from .news.service import refresh_keyword

    client = get_client()
    # API 키가 새로 생기면(client 있음/없음이 바뀌면) 30분을 기다리지 않고 바로 요약하도록 키에 포함
    fetched, key = _news_fetched_at(), (keyword, days, client is not None)
    if not force and time.time() - fetched.get(key, 0) < NEWS_REFRESH_SECONDS:
        return None
    result = refresh_keyword(get_store(), keyword, client, days=days)
    if not result.error:
        fetched[key] = time.time()
    return result


def forget_keyword_news(keyword: str) -> None:
    """키워드를 지웠다가 다시 추가하면 바로 새로 모으도록 기록을 지운다."""
    fetched = _news_fetched_at()
    for key in [k for k in fetched if k[0] == keyword]:
        del fetched[key]


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
