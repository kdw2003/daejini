"""질문 의도 분류. 키워드 점수 + 개체(종목·통화·용어) 인식으로 의도를 고른다."""
import json
from dataclasses import dataclass, field
from pathlib import Path

from .nlp import tokenize, normalize

DATA = Path(__file__).resolve().parent.parent / "data"


def _load(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


INTENTS = _load("intents.json")
TICKERS = _load("tickers.json")
CURRENCIES = _load("currencies.json")
GLOSSARY = _load("glossary.json")

# 개체가 발견되면 해당 의도에 가산점
ENTITY_WEIGHT = 2


@dataclass
class Parsed:
    intent: str
    entities: dict = field(default_factory=dict)
    tokens: list = field(default_factory=list)


def _find(text_norm: str, table: dict) -> list[str]:
    # 긴 이름부터 찾아서 짧은 이름이 중복으로 잡히지 않게 함
    found = []
    for name in sorted(table, key=len, reverse=True):
        key = normalize(name)
        if key in text_norm and not any(key in normalize(f) for f in found):
            found.append(name)
    return found


def parse(text: str) -> Parsed:
    tokens = tokenize(text)
    norm = normalize(text)

    entities = {
        "stock": _find(norm, TICKERS),
        "currency": _find(norm, CURRENCIES),
        "term": _find(norm, GLOSSARY),
    }

    scores = {intent: sum(tok in kws for tok in tokens) for intent, kws in INTENTS.items()}
    scores["stock_price"] += ENTITY_WEIGHT * bool(entities["stock"])
    scores["exchange_rate"] += ENTITY_WEIGHT * bool(entities["currency"])
    # '뭐'는 일상 대화에도 흔해서, 경제 용어가 있을 때만 용어 질문으로 본다
    scores["glossary"] = scores["glossary"] + ENTITY_WEIGHT if entities["term"] else 0

    best = max(scores, key=scores.get)
    intent = best if scores[best] > 0 else "unknown"
    return Parsed(intent, entities, tokens)
