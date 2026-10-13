"""메인 화면용 미국 증시 뉴스: 한국어 기사 헤드라인을 모아 3줄 요약.

관심 키워드 목록(keywords 테이블)에는 넣지 않아 뉴스 브리핑 화면에는 나타나지 않는다.
"""
from .fetch import fetch_keyword
from .service import refresh_keyword, since_iso

MARKET_KEY = "미국 증시"
MARKET_QUERY = "뉴욕증시 OR 나스닥 OR S&P500"


def _fetch_market(keyword, days):
    return fetch_keyword(MARKET_QUERY, days=days, limit=25)


def refresh_market(store, client):
    return refresh_keyword(store, MARKET_KEY, client, days=1, fetcher=_fetch_market)


def market_news(store, limit: int = 5) -> tuple[dict | None, list[dict]]:
    """(요약, 최신 기사 목록)"""
    return store.summary(MARKET_KEY), store.recent_articles(MARKET_KEY, since_iso(1), limit=limit)
