"""Claude로 기업 브리핑: 지표·업종 중간값·최근 뉴스 분류를 바탕으로 강점·약점·체크포인트."""
from pydantic import BaseModel, ValidationError

from ..news.analyze import MODEL, AnalysisError
from .metrics import METRIC_INFO, fmt_metric, fmt_money

SYSTEM = """당신은 한국 개인 투자자를 돕는 기업 분석가입니다. 주로 미국 기업을 다룹니다.
한 기업의 재무 지표, 같은 업종 중간값, 최근 뉴스 분류 결과를 받아 짧은 브리핑을 씁니다.

- headline: 이 기업의 현재 상태를 한 문장으로
- strengths: 강점 2~3개
- weaknesses: 약점이나 위험 2~3개
- checkpoints: 앞으로 확인할 것 2~3개 (예: 다음 실적 발표에서 볼 지표, 업황 변수)

각 항목은 한 문장이고, 주어진 숫자를 근거로 씁니다. 주어진 자료에 없는 사실은 지어내지 않습니다.
업종 중간값과 비교할 때는 금융업처럼 지표 해석이 다른 경우를 고려합니다.
매수·매도 권유나 목표 주가는 쓰지 않습니다."""

SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "strengths": {"type": "array", "items": {"type": "string"}},
        "weaknesses": {"type": "array", "items": {"type": "string"}},
        "checkpoints": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["headline", "strengths", "weaknesses", "checkpoints"],
    "additionalProperties": False,
}


class Briefing(BaseModel):
    headline: str
    strengths: list[str]
    weaknesses: list[str]
    checkpoints: list[str]


def build_prompt(snap, sector_avg: dict, news: list[dict]) -> str:
    lines = [f"기업: {snap.name} ({snap.ticker}), 업종: {snap.sector}",
             f"시가총액: {fmt_money(snap.market_cap, snap.currency)}", "", "핵심 지표 (업종 중간값):"]
    for key, (label, *_rest) in METRIC_INFO.items():
        value = fmt_metric(key, getattr(snap.metrics, key), snap.metrics.loss)
        avg = fmt_metric(key, sector_avg.get(key))
        lines.append(f"- {label}: {value} (업종 중간값 {avg})")
    lines += ["", "연간 실적:"]
    for a in snap.annuals[:4]:
        lines.append(f"- {a.year} 회계연도: 매출 {fmt_money(a.revenue, snap.currency)}, "
                     f"영업이익 {fmt_money(a.operating_income, snap.currency)}, 순이익 {fmt_money(a.net_income, snap.currency)}")
    lines += ["", "최근 뉴스 (AI 분류):"]
    analyzed = [n for n in news if n.get("sentiment")]
    if analyzed:
        for n in analyzed[:15]:
            lines.append(f"- [{n['sentiment']}·영향 {n['impact']}] {n['title']}")
    else:
        lines.append("- 분류된 뉴스 없음")
    return "\n".join(lines)


def brief(client, snap, sector_avg: dict, news: list[dict], model: str = MODEL) -> Briefing:
    response = client.beta.messages.create(
        model=model,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
        system=SYSTEM,
        messages=[{"role": "user", "content": build_prompt(snap, sector_avg, news)}],
    )
    if response.stop_reason == "refusal":
        raise AnalysisError("모델이 이 요청의 분석을 거절했어요.")
    if response.stop_reason == "max_tokens":
        raise AnalysisError("응답이 길이 제한에 걸려 잘렸어요.")
    text = next((b.text for b in response.content if b.type == "text"), None)
    if text is None:
        raise AnalysisError("응답에 분석 결과가 없어요.")
    try:
        return Briefing.model_validate_json(text)
    except ValidationError as e:
        raise AnalysisError(f"분석 결과 형식이 맞지 않아요: {e.error_count()}개 오류") from e
