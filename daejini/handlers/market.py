"""주가·지수·환율 조회 (yfinance)."""
from ..router import TICKERS, CURRENCIES


def _quote(symbol: str):
    import yfinance as yf

    hist = yf.Ticker(symbol).history(period="5d")
    if len(hist) < 2:
        raise ValueError("데이터 부족")
    last, prev = hist["Close"].iloc[-1], hist["Close"].iloc[-2]
    return last, (last - prev) / prev * 100


def _fmt(name, symbol, unit=""):
    try:
        price, change = _quote(symbol)
    except Exception:
        return f"{name}: 지금은 시세를 가져올 수 없어요."
    arrow = "▲" if change >= 0 else "▼"
    return f"{name}: {price:,.2f}{unit} ({arrow} {abs(change):.2f}%)"


def stock(parsed) -> str:
    names = parsed.entities["stock"] or ["코스피"]
    return "\n".join(_fmt(n, TICKERS[n]) for n in names)


def exchange(parsed) -> str:
    names = parsed.entities["currency"] or ["달러"]
    return "\n".join(_fmt(f"{n}/원", CURRENCIES[n], "원") for n in names)
