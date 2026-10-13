"""키워드별 뉴스 수집 (구글 뉴스 RSS 검색, API 키 불필요)."""
import calendar
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import quote

SEARCH_URL = "https://news.google.com/rss/search?q={query}&hl=ko&gl=KR&ceid=KR:ko"


@dataclass
class Article:
    url: str
    title: str
    source: str
    published: str  # ISO 8601, UTC


def search_url(keyword: str, days: int) -> str:
    return SEARCH_URL.format(query=quote(f"{keyword} when:{days}d"))


def _published(entry) -> str:
    parsed = entry.get("published_parsed")
    if not parsed:
        return ""
    ts = calendar.timegm(parsed)
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _clean_title(title: str, source: str) -> str:
    # 구글 뉴스 제목은 "제목 - 언론사" 형식
    suffix = f" - {source}"
    return title[: -len(suffix)] if source and title.endswith(suffix) else title


def parse_feed(feed, limit: int = 20) -> list[Article]:
    articles, seen_titles = [], set()
    for entry in feed.entries:
        source = entry.get("source", {}).get("title", "")
        title = _clean_title(entry.get("title", "").strip(), source)
        link = entry.get("link", "")
        # 같은 기사가 여러 매체에 실리면 제목이 같으므로 한 번만
        if not title or not link or title in seen_titles:
            continue
        seen_titles.add(title)
        articles.append(Article(url=link, title=title, source=source, published=_published(entry)))
        if len(articles) >= limit:
            break
    return articles


def fetch_keyword(keyword: str, days: int = 2, limit: int = 20) -> list[Article]:
    import feedparser

    feed = feedparser.parse(search_url(keyword, days))
    if feed.get("bozo") and not feed.entries:
        raise ConnectionError(f"'{keyword}' 뉴스를 가져오지 못했어요: {feed.get('bozo_exception')}")
    return parse_feed(feed, limit)
