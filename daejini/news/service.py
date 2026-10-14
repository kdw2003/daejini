"""뉴스 새로고침: 수집 → 저장 → (새 기사가 있으면) 분석."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .analyze import SUMMARY_MODEL, AnalysisError, analyze
from .fetch import fetch_keyword


@dataclass
class KeywordResult:
    keyword: str
    new_articles: int = 0
    analyzed: bool = False
    error: str = ""


def since_iso(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def api_error_message(e: Exception) -> str:
    import anthropic

    if isinstance(e, anthropic.AuthenticationError):
        return "API 키가 올바르지 않아요. .env의 ANTHROPIC_API_KEY를 확인하세요."
    if isinstance(e, anthropic.PermissionDeniedError):
        return "이 API 키로는 모델을 쓸 권한이 없어요."
    if isinstance(e, anthropic.RateLimitError):
        return "요청이 너무 많아요. 잠시 후 다시 시도하세요."
    if isinstance(e, anthropic.APIStatusError):
        return f"Claude API 오류({e.status_code})로 분석하지 못했어요."
    if isinstance(e, anthropic.APIConnectionError):
        return "Claude API에 연결하지 못했어요. 인터넷 연결을 확인하세요."
    return f"분석하지 못했어요: {e}"


def refresh_keyword(store, keyword, client=None, days=2, fetcher=fetch_keyword, model=SUMMARY_MODEL):
    result = KeywordResult(keyword)
    try:
        result.new_articles = store.save_articles(keyword, fetcher(keyword, days=days))
    except Exception as e:  # 네트워크·피드 오류는 키워드 하나만 실패로 표시
        result.error = f"뉴스를 가져오지 못했어요: {e}"
        return result

    if client is None:
        return result

    articles = store.recent_articles(keyword, since_iso(days))
    if not articles:
        return result
    ids = sorted(a["id"] for a in articles)
    previous = store.summary(keyword)
    if previous and previous["article_ids"] == ids:
        return result  # 기사 목록이 그대로면 다시 분석하지 않음 (비용 절약)

    try:
        report = analyze(client, keyword, articles, model=model)
    except AnalysisError as e:
        result.error = str(e)
        return result
    except Exception as e:
        result.error = api_error_message(e)
        return result
    store.save_report(keyword, report, ids, model)
    result.analyzed = True
    return result


def make_client():
    """API 키가 없으면 None (뉴스 수집만 동작)."""
    import os

    import anthropic

    if not os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return None
    return anthropic.Anthropic()
