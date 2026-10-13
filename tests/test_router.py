import pytest

from daejini.router import parse


@pytest.mark.parametrize("text, intent", [
    ("삼성전자 주가 얼마야?", "stock_price"),
    ("오늘 코스피 어때", "stock_price"),
    ("달러 환율 알려줘", "exchange_rate"),
    ("엔화 얼마야", "exchange_rate"),
    ("경제 뉴스 보여줘", "news"),
    ("PER 뜻이 뭐야", "glossary"),
    ("기준금리가 뭐야?", "glossary"),
    ("도움말", "help"),
    ("오늘 저녁 뭐 먹지", "unknown"),
])
def test_intent(text, intent):
    assert parse(text).intent == intent


def test_longest_entity_wins():
    assert parse("SK하이닉스 주가").entities["stock"] == ["SK하이닉스"]
