"""Claude로 기술적 지표와 백테스트 결과를 쉬운 말로 해설."""
from pydantic import BaseModel, ValidationError

from ..news.analyze import MODEL, AnalysisError

SYSTEM = """당신은 주식 초보자에게 기술적 분석 결과를 설명하는 강사입니다.
한 종목의 현재 지표 상태, 지지·저항 참고 구간, 과거 3~5년 백테스트 결과를 받아 해설합니다.

- summary: 지금 차트가 어떤 상태인지 두 문장 이내로
- points: 근거 3~4개. 각 지표가 무엇을 말하는지 숫자와 함께 한 문장씩
- backtest: 이 종목에서 어떤 방식이 과거에 통했고 어떤 방식이 안 통했는지, 단순 보유와 비교해 두 문장 이내로
- caution: 이 분석의 한계 한 문장 (예: 과거 성과가 미래를 보장하지 않음, 표본 거래 수가 적음)

주어진 숫자만 근거로 씁니다. 매수·매도 권유, 목표 주가, "지금 사세요" 같은 표현은 쓰지 않습니다."""

SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "points": {"type": "array", "items": {"type": "string"}},
        "backtest": {"type": "string"},
        "caution": {"type": "string"},
    },
    "required": ["summary", "points", "backtest", "caution"],
    "additionalProperties": False,
}


class Commentary(BaseModel):
    summary: str
    points: list[str]
    backtest: str
    caution: str


def build_prompt(name: str, signals, z, results: dict, years: int, currency: str = "USD") -> str:
    from ..company.metrics import fmt_price

    lines = [f"종목: {name}", "", "현재 지표 상태:"]
    lines += [f"- {s.name}: {s.state} ({s.detail})" for s in signals]
    lines += ["", "참고 구간 (최근 120일 저점·고점 기준):"]
    if z is None:
        lines.append("- 계산할 데이터가 부족함")
    else:
        lines.append(f"- 현재가 {fmt_price(z.price, currency)}, 하루 평균 변동폭(ATR) {fmt_price(z.atr, currency)}")
        lines.append(f"- 지지선 {fmt_price(z.support, currency)}" if z.support else "- 지지선 없음 (최근 120일 저점보다 아래)")
        lines.append(f"- 저항선 {fmt_price(z.resistance, currency)}" if z.resistance else "- 저항선 없음 (최근 120일 고점보다 위)")
    lines += ["", f"최근 {years}년 백테스트 (수수료·세금 반영):"]
    for label, r in results.items():
        win = f"{r.win_rate:.0f}%" if r.win_rate is not None else "—"
        lines.append(f"- {label}: 총수익률 {r.total_return:+.1f}%, 최대낙폭 {r.mdd:.1f}%, "
                     f"거래 {len(r.trades)}회, 승률 {win}")
    return "\n".join(lines)


def explain(client, name, signals, z, results: dict, years: int, currency: str = "USD", model: str = MODEL) -> Commentary:
    response = client.beta.messages.create(
        model=model,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        system=SYSTEM,
        messages=[{"role": "user", "content": build_prompt(name, signals, z, results, years, currency)}],
    )
    if response.stop_reason == "refusal":
        raise AnalysisError("모델이 이 요청의 분석을 거절했어요.")
    if response.stop_reason == "max_tokens":
        raise AnalysisError("응답이 길이 제한에 걸려 잘렸어요.")
    text = next((b.text for b in response.content if b.type == "text"), None)
    if text is None:
        raise AnalysisError("응답에 분석 결과가 없어요.")
    try:
        return Commentary.model_validate_json(text)
    except ValidationError as e:
        raise AnalysisError(f"분석 결과 형식이 맞지 않아요: {e.error_count()}개 오류") from e
