import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import feedparser
import pytest

from daejini.news.analyze import AnalysisError, Report, analyze, build_prompt
from daejini.news.fetch import Article, parse_feed, search_url
from daejini.news.service import refresh_keyword
from daejini.news.store import Store

FIXTURE = Path(__file__).parent / "fixtures" / "google_news.xml"


def recent(hours=1):
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


class FakeClient:
    """client.beta.messages.create 만 흉내 낸다."""

    def __init__(self, payload=None, stop_reason="end_turn"):
        self.calls = []
        self.payload, self.stop_reason = payload, stop_reason
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))
        self.messages = SimpleNamespace(create=self._create)  # Haiku는 beta가 아닌 일반 엔드포인트

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        text = self.payload if isinstance(self.payload, str) else json.dumps(self.payload, ensure_ascii=False)
        return SimpleNamespace(stop_reason=self.stop_reason, content=[SimpleNamespace(type="text", text=text)])


# 수집
def test_parse_feed_strips_source_and_dedupes_titles():
    articles = parse_feed(feedparser.parse(FIXTURE.read_text(encoding="utf-8")))
    assert [a.title for a in articles] == ["삼성전자, 3분기 영업이익 12조 돌파", "외국인 2조 매도에 반도체주 급락"]
    assert articles[0].source == "한국경제"
    assert articles[0].published.startswith("2026-10-12T23:10:00")


def test_search_url_encodes_keyword_and_period():
    url = search_url("SK하이닉스", 3)
    assert "SK%ED%95%98" in url and "when%3A3d" in url


# 저장
def test_store_keywords_and_articles():
    store = Store(":memory:")
    assert store.add_keyword(" 삼성전자 ") and not store.add_keyword("삼성전자")
    arts = [Article("https://a", "제목1", "한경", recent()), Article("https://b", "제목2", "매경", recent(2))]
    assert store.save_articles("삼성전자", arts) == 2
    assert store.save_articles("삼성전자", arts) == 0  # 이미 있는 기사
    assert store.save_articles("반도체", arts[:1]) == 1  # 같은 기사, 다른 키워드
    rows = store.recent_articles("삼성전자", recent(24))
    assert [r["title"] for r in rows] == ["제목1", "제목2"] and rows[0]["sentiment"] is None
    store.remove_keyword("삼성전자")
    assert store.keywords() == [] and store.recent_articles("삼성전자", recent(24)) == []


# 분석
ARTICLES = [
    {"id": 1, "title": "삼성전자 영업이익 12조 돌파", "source": "한경", "published": "2026-10-12T23:10:00+00:00"},
    {"id": 2, "title": "외국인 매도에 반도체주 급락", "source": "연합", "published": "2026-10-12T07:00:00+00:00"},
]
PAYLOAD = {
    "summary": ["3분기 실적 예상 상회", "외국인 매도로 주가 약세", "반도체 업황 논쟁", "넷째 줄"],
    "verdicts": [
        {"id": 1, "sentiment": "호재", "impact": 3, "target": "삼성전자", "reason": "실적 개선"},
        {"id": 2, "sentiment": "악재", "impact": 2, "target": "반도체", "reason": "수급 악화"},
        {"id": 99, "sentiment": "호재", "impact": 1, "target": "?", "reason": "목록에 없는 id"},
        {"id": 1, "sentiment": "악재", "impact": 1, "target": "중복", "reason": "중복 id"},
    ],
}


def test_build_prompt_lists_ids_sources_dates():
    prompt = build_prompt("삼성전자", ARTICLES)
    assert "[1] (한경, 2026-10-12) 삼성전자 영업이익 12조 돌파" in prompt


def test_analyze_parses_and_cleans_report():
    client = FakeClient(PAYLOAD)
    report = analyze(client, "삼성전자", ARTICLES)
    assert len(report.summary) == 3
    assert [(v.id, v.sentiment) for v in report.verdicts] == [(1, "호재"), (2, "악재")]
    call = client.calls[0]
    assert call["model"] == "claude-haiku-5-5"  # 뉴스 요약은 Haiku 5.5
    assert "fallbacks" not in call and "betas" not in call  # Haiku는 서버 측 대체 모델 미지원
    assert "temperature" not in call  # Haiku 5.5는 기본값이 아닌 temperature를 거부
    assert call["output_config"]["format"]["type"] == "json_schema"


def test_analyze_with_opus_keeps_fallbacks():
    client = FakeClient(PAYLOAD)
    analyze(client, "삼성전자", ARTICLES, model="claude-opus-5-5")
    call = client.calls[0]
    assert call["fallbacks"] == "default" and call["betas"] == ["server-side-fallback-2026-07-01"]


@pytest.mark.parametrize("client", [
    FakeClient(PAYLOAD, stop_reason="refusal"),
    FakeClient(PAYLOAD, stop_reason="max_tokens"),
    FakeClient("{not json"),
    FakeClient({"summary": [], "verdicts": [{"id": 1, "sentiment": "대박", "impact": 3, "target": "", "reason": ""}]}),
])
def test_analyze_rejects_unusable_responses(client):
    with pytest.raises(AnalysisError):
        analyze(client, "삼성전자", ARTICLES)


# 새로고침 흐름
def test_refresh_saves_analysis_and_skips_when_unchanged():
    store = Store(":memory:")
    fetched = [Article("https://a", "삼성전자 영업이익 12조 돌파", "한경", recent()),
               Article("https://b", "외국인 매도에 반도체주 급락", "연합", recent(2))]
    fetcher = lambda kw, days: fetched
    client = FakeClient(PAYLOAD)

    r = refresh_keyword(store, "삼성전자", client, fetcher=fetcher)
    assert r.new_articles == 2 and r.analyzed and not r.error
    rows = {row["title"]: row for row in store.recent_articles("삼성전자", recent(24))}
    assert rows["삼성전자 영업이익 12조 돌파"]["sentiment"] == "호재"
    assert store.summary("삼성전자")["lines"][0] == "3분기 실적 예상 상회"

    r2 = refresh_keyword(store, "삼성전자", client, fetcher=fetcher)
    assert r2.new_articles == 0 and not r2.analyzed and len(client.calls) == 1


def test_refresh_without_client_only_collects():
    store = Store(":memory:")
    r = refresh_keyword(store, "금리", None, fetcher=lambda kw, days: [Article("https://a", "기준금리 동결", "한경", recent())])
    assert r.new_articles == 1 and not r.analyzed


def test_refresh_reports_fetch_errors():
    def broken(kw, days):
        raise ConnectionError("timeout")
    r = refresh_keyword(Store(":memory:"), "금리", None, fetcher=broken)
    assert "가져오지 못했어요" in r.error


def test_market_news_is_hidden_from_keyword_list(monkeypatch):
    from daejini.news import market

    monkeypatch.setattr(market, "_fetch_market", lambda kw, days: [Article("https://m", "코스피 급락", "한경", recent())])
    store = Store(":memory:")
    store.add_keyword("삼성전자")
    r = market.refresh_market(store, FakeClient(PAYLOAD | {"verdicts": []}))
    summary, articles = market.market_news(store)
    assert r.new_articles == 1 and r.analyzed
    assert [a["title"] for a in articles] == ["코스피 급락"] and summary["lines"][0] == "3분기 실적 예상 상회"
    assert store.keywords() == ["삼성전자"]  # 뉴스 브리핑 키워드 목록에는 안 보임
