from daejini import ui
from daejini.news import service
from daejini.news.service import KeywordResult


def test_news_refresh_skips_after_success_but_retries_after_failure(monkeypatch):
    calls = []

    def fake_refresh(store, keyword, client, days):
        calls.append(keyword)
        return KeywordResult(keyword, error="일시적 오류" if len(calls) == 1 else "")

    monkeypatch.setattr(service, "refresh_keyword", fake_refresh)
    monkeypatch.setattr(ui, "get_store", lambda: None)
    monkeypatch.setattr(ui, "get_client", lambda: None)
    ui._news_fetched_at().clear()

    assert ui.refresh_keyword_news("엔비디아", 2).error  # 1회차: 실패
    assert ui.refresh_keyword_news("엔비디아", 2).error == ""  # 실패는 기억하지 않아 바로 재시도
    assert ui.refresh_keyword_news("엔비디아", 2) is None  # 성공 뒤 30분 안에는 다시 안 모음
    assert ui.refresh_keyword_news("엔비디아", 2, force=True) is not None  # 새로고침 버튼은 강제
    ui.forget_keyword_news("엔비디아")
    assert ui.refresh_keyword_news("엔비디아", 2) is not None  # 키워드를 지웠다 다시 추가한 경우
    assert len(calls) == 4


def test_news_refresh_reruns_when_api_key_appears(monkeypatch):
    calls = []
    monkeypatch.setattr(service, "refresh_keyword", lambda store, kw, client, days: calls.append(client) or KeywordResult(kw))
    monkeypatch.setattr(ui, "get_store", lambda: None)
    ui._news_fetched_at().clear()
    monkeypatch.setattr(ui, "get_client", lambda: None)
    ui.refresh_keyword_news("테슬라", 2)
    assert ui.refresh_keyword_news("테슬라", 2) is None  # 키 없이 30분 안: 다시 안 모음
    monkeypatch.setattr(ui, "get_client", lambda: "client")
    assert ui.refresh_keyword_news("테슬라", 2) is not None  # 키가 생기면 바로 요약
    assert calls == [None, "client"]
