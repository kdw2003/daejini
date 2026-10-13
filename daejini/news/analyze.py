"""Claude로 키워드별 뉴스 요약과 호재·악재 분류."""
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

MODEL = "claude-opus-5-5"

SYSTEM = """당신은 한국 개인 투자자를 돕는 증권 뉴스 분석가입니다.
관심 키워드(종목, 산업, 경제 주제)와 관련 기사 제목 목록을 받아 두 가지를 합니다.

1. summary: 기사들에서 반복해서 나오는 핵심 이슈를 3줄 이내로 요약합니다.
   한 줄에 한 이슈, 숫자와 고유명사를 살려서 짧게 씁니다.
2. verdicts: 기사마다 이 키워드의 주가에 미칠 영향을 판단합니다.
   - sentiment: "호재"(주가에 긍정적일 가능성이 큼), "악재"(부정적일 가능성이 큼), "중립"(영향이 불분명하거나 관련이 적음)
   - impact: 1(약함), 2(보통), 3(강함). 실적, 규제, 대형 계약, 소송처럼 펀더멘털을 바꾸는 소식일수록 큽니다.
   - target: 영향을 받는 종목이나 산업 이름
   - reason: 판단 근거 한 문장

기사 본문 없이 제목만 보고 판단합니다. 제목만으로 방향을 알 수 없으면 추측하지 말고 "중립"으로 둡니다.
매수·매도 권유는 하지 않습니다. 목록에 있는 모든 기사 id에 대해 verdict를 하나씩 냅니다."""

SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "array", "items": {"type": "string"}},
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "sentiment": {"type": "string", "enum": ["호재", "악재", "중립"]},
                    "impact": {"type": "integer", "enum": [1, 2, 3]},
                    "target": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["id", "sentiment", "impact", "target", "reason"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summary", "verdicts"],
    "additionalProperties": False,
}


class Verdict(BaseModel):
    id: int
    sentiment: Literal["호재", "악재", "중립"]
    impact: int = Field(ge=1, le=3)
    target: str
    reason: str


class Report(BaseModel):
    summary: list[str]
    verdicts: list[Verdict]


class AnalysisError(Exception):
    """분석 결과를 쓸 수 없을 때 (거절, 잘림, 형식 오류)."""


def build_prompt(keyword: str, articles: list[dict]) -> str:
    lines = [f"키워드: {keyword}", "", "기사 목록:"]
    for a in articles:
        day = (a.get("published") or "")[:10]
        lines.append(f"[{a['id']}] ({a.get('source') or '출처 미상'}, {day}) {a['title']}")
    return "\n".join(lines)


def analyze(client, keyword: str, articles: list[dict], model: str = MODEL) -> Report:
    """articles: id, title, source, published 를 가진 dict 목록."""
    response = client.beta.messages.create(
        model=model,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        system=SYSTEM,
        messages=[{"role": "user", "content": build_prompt(keyword, articles)}],
    )
    if response.stop_reason == "refusal":
        raise AnalysisError("모델이 이 요청의 분석을 거절했어요.")
    if response.stop_reason == "max_tokens":
        raise AnalysisError("응답이 길이 제한에 걸려 잘렸어요. 기사 수를 줄여 보세요.")

    text = next((b.text for b in response.content if b.type == "text"), None)
    if text is None:
        raise AnalysisError("응답에 분석 결과가 없어요.")
    try:
        report = Report.model_validate_json(text)
    except ValidationError as e:
        raise AnalysisError(f"분석 결과 형식이 맞지 않아요: {e.error_count()}개 오류") from e

    # 목록에 없는 id는 버리고, 같은 id가 두 번 오면 처음 것만 쓴다
    known, seen, verdicts = {a["id"] for a in articles}, set(), []
    for v in report.verdicts:
        if v.id in known and v.id not in seen:
            seen.add(v.id)
            verdicts.append(v)
    return Report(summary=report.summary[:3], verdicts=verdicts)
