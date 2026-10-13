"""경제 뉴스 헤드라인 (RSS)."""

# 언론사 RSS 주소는 바뀔 수 있으니 실행 전 확인
FEEDS = {
    "한국경제": "https://www.hankyung.com/feed/economy",
    "매일경제": "https://www.mk.co.kr/rss/30100041/",
}


def answer(parsed, limit: int = 3) -> str:
    import feedparser

    lines = []
    for source, url in FEEDS.items():
        feed = feedparser.parse(url)
        for entry in feed.entries[:limit]:
            lines.append(f"- [{source}] {entry.title}")
    return "\n".join(lines) or "지금은 뉴스를 불러올 수 없어요."
