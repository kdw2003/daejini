"""기업 목록과 시세·재무 데이터 (yfinance, API 키 불필요)."""
import json
import math
from pathlib import Path

from .metrics import Annual, Snapshot, compute, currency_of

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
COMPANIES_FILE = DATA_DIR / "companies.json"
ETFS_FILE = DATA_DIR / "etfs.json"

INCOME_ROWS = {
    "revenue": ["Total Revenue"],
    "operating_income": ["Operating Income"],
    "net_income": ["Net Income Common Stockholders", "Net Income"],
}
BALANCE_ROWS = {
    "equity": ["Stockholders Equity", "Common Stock Equity"],
    "liabilities": ["Total Liabilities Net Minority Interest"],
}


def load_companies() -> dict[str, dict[str, str]]:
    """{산업: {기업명: 티커}}"""
    return json.loads(COMPANIES_FILE.read_text(encoding="utf-8"))


def company_index() -> dict[str, tuple[str, str]]:
    """{기업명: (티커, 산업)}"""
    return {name: (ticker, sector)
            for sector, members in load_companies().items()
            for name, ticker in members.items()}


def load_etfs() -> dict[str, str]:
    """{티커: 설명}"""
    return json.loads(ETFS_FILE.read_text(encoding="utf-8"))


def search_options() -> dict[str, tuple[str, str]]:
    """포트폴리오 검색 목록 {티커: (표시 이름, 업종)}. 기업 + ETF."""
    options = {ticker: (name, sector) for name, (ticker, sector) in company_index().items()}
    for ticker, desc in load_etfs().items():
        options[ticker] = (f"{ticker} ({desc})", "ETF")
    return options


def normalize_ticker(text: str) -> list[str]:
    """사용자가 입력한 티커 후보. 6자리 숫자면 한국 종목으로 보고 코스피·코스닥 둘 다 시도."""
    t = text.strip().upper()
    if t.isdigit() and len(t) == 6:
        return [f"{t}.KS", f"{t}.KQ"]
    return [t] if t else []


def resolve_query(text: str, options: dict[str, tuple[str, str]]) -> list[str]:
    """검색창 입력 → 티커 후보. 티커, 기업 이름(완전 일치 → 한 곳만 포함), 6자리 한국 코드 순으로 찾는다."""
    q = text.strip()
    if not q:
        return []
    if q.upper() in options:
        return [q.upper()]
    key = q.replace(" ", "").lower()
    names = {t: name.replace(" ", "").lower() for t, (name, _sector) in options.items()}
    exact = [t for t, n in names.items() if n == key]
    if exact:
        return exact
    partial = [t for t, n in names.items() if key in n]
    if len(partial) == 1:
        return partial
    return normalize_ticker(q)


def lookup(ticker: str) -> dict | None:
    """종목 확인: 이름, 현재가, 전일 종가, 통화. 시세가 없으면 None."""
    import yfinance as yf

    t = yf.Ticker(ticker)
    try:
        fi = t.fast_info
        price, prev = fi.last_price, fi.previous_close
    except Exception:
        return None
    if not price:
        return None
    try:
        info = t.info
        name = info.get("shortName") or info.get("longName") or ticker
        kind = info.get("quoteType", "")
    except Exception:
        name, kind = ticker, ""
    return {"ticker": ticker, "name": name, "price": price, "prev": prev,
            "currency": currency_of(ticker), "is_etf": kind == "ETF"}


def _value(frame, names, column):
    for name in names:
        if name in frame.index:
            v = frame.at[name, column]
            if v is not None and not (isinstance(v, float) and math.isnan(v)):
                return float(v)
    return None


def annuals_from_frames(income, balance) -> list[Annual]:
    """yfinance income_stmt / balance_sheet → 최신 연도 순 Annual 목록."""
    result = []
    for col in income.columns:
        a = Annual(year=col.year)
        for attr, names in INCOME_ROWS.items():
            setattr(a, attr, _value(income, names, col))
        if col in balance.columns:
            for attr, names in BALANCE_ROWS.items():
                setattr(a, attr, _value(balance, names, col))
        # 값이 하나도 없는 연도(yfinance가 빈 열을 주는 경우)는 뺀다
        if any(getattr(a, f) is not None for f in ("revenue", "net_income", "equity")):
            result.append(a)
    return sorted(result, key=lambda a: a.year, reverse=True)


def fetch_snapshot(name: str, ticker: str, sector: str) -> Snapshot:
    import yfinance as yf

    snap = Snapshot(name=name, ticker=ticker, sector=sector, currency=currency_of(ticker))
    try:
        t = yf.Ticker(ticker)
        fi = t.fast_info
        snap.price = fi.last_price
        snap.market_cap = fi.market_cap
        snap.year_high, snap.year_low = fi.year_high, fi.year_low
        snap.annuals = annuals_from_frames(t.income_stmt, t.balance_sheet)
    except Exception as e:
        snap.error = f"{name} 데이터를 가져오지 못했어요: {e}"
        return snap
    snap.metrics = compute(snap.annuals, snap.market_cap)
    return snap


def fetch_quote(ticker: str) -> tuple[float | None, float | None]:
    """(현재가, 전일 종가)"""
    import yfinance as yf

    fi = yf.Ticker(ticker).fast_info
    return fi.last_price, fi.previous_close


def fetch_board(tickers: list[str], period: str = "1mo") -> dict[str, dict]:
    """여러 종목·지수의 현재가, 전일 종가, 최근 종가 목록(미니 차트용)을 한 번에.

    일봉 데이터는 하루씩 빠지는 날이 있어 등락률은 fast_info의 전일 종가로 계산한다.
    """
    from concurrent.futures import ThreadPoolExecutor

    import yfinance as yf

    daily = yf.download(tickers, period=period, interval="1d", auto_adjust=True,
                        progress=False, group_by="ticker", threads=True)

    def quote(t):
        try:
            fi = yf.Ticker(t).fast_info
            return t, fi.last_price, fi.previous_close
        except Exception:
            return t, None, None

    with ThreadPoolExecutor(max_workers=8) as ex:
        quotes = list(ex.map(quote, tickers))

    board = {}
    for t, last, prev in quotes:
        try:
            closes = daily[t]["Close"].dropna().tolist()
        except KeyError:
            closes = []
        if last is None and closes:
            last = closes[-1]
        if last is None:
            continue
        if closes:
            closes[-1] = last  # 장중이면 마지막 점을 현재가로
        board[t] = {
            "price": last,
            "prev": prev,
            "change_pct": (last / prev - 1) * 100 if prev else None,
            "closes": closes,
        }
    return board


def fetch_ohlc(ticker: str, period: str = "5y"):
    """일봉. 열: date, open, high, low, close, volume (수정주가)"""
    import yfinance as yf

    h = yf.Ticker(ticker).history(period=period, auto_adjust=True)
    df = h[["Open", "High", "Low", "Close", "Volume"]].rename(columns=str.lower)
    df.index = df.index.tz_localize(None)
    return df.reset_index(names="date")


def fetch_history(ticker: str, period: str = "1y"):
    """일별 종가와 20·60일 이동평균. 열: date, close, ma20, ma60"""
    import yfinance as yf

    h = yf.Ticker(ticker).history(period=period, auto_adjust=True)
    df = h[["Close"]].rename(columns={"Close": "close"})
    df["ma20"] = df["close"].rolling(20).mean()
    df["ma60"] = df["close"].rolling(60).mean()
    df.index = df.index.tz_localize(None)
    return df.reset_index(names="date")
