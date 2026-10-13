from .router import parse
from .handlers import glossary, market, news

HELP = (
    "이런 걸 물어볼 수 있어요.\n"
    "- 삼성전자 주가 얼마야?\n"
    "- 오늘 달러 환율 알려줘\n"
    "- 경제 뉴스 보여줘\n"
    "- 기준금리가 뭐야?"
)

HANDLERS = {
    "stock_price": market.stock,
    "exchange_rate": market.exchange,
    "news": news.answer,
    "glossary": glossary.answer,
    "help": lambda p: HELP,
}


def reply(text: str) -> str:
    parsed = parse(text)
    handler = HANDLERS.get(parsed.intent)
    if handler is None:
        return "잘 모르겠어요. '도움말'이라고 입력하면 할 수 있는 걸 알려드려요."
    return handler(parsed)
