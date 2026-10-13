"""메인 화면: 시장 지수, 오늘의 시장 뉴스 3줄 요약, 주요 종목 시세, 바로가기."""
from datetime import datetime

import streamlit as st

from daejini import ui
from daejini.company.data import company_index, search_options
from daejini.company.metrics import currency_of, fmt_krw, fmt_price
from daejini.news.market import market_news
from daejini.portfolio.valuation import evaluate

INDICES = [("S&P 500", "^GSPC", ""), ("나스닥", "^IXIC", ""), ("다우존스", "^DJI", ""),
           ("필라델피아 반도체", "^SOX", ""), ("원/달러", "KRW=X", "원")]
DEFAULT_STOCKS = ["NVDA", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "AVGO"]
MAX_STOCKS = 8
WEEKDAYS = "월화수목금토일"

SHORTCUTS = [
    ("views/news.py", ":material/newspaper:", "뉴스 브리핑", "관심 키워드 뉴스 요약과 호재·악재"),
    ("views/company.py", ":material/domain:", "기업 분석", "핵심 지표, 실적, 공시, AI 브리핑"),
    ("views/sector.py", ":material/compare_arrows:", "산업 비교", "같은 업종 기업 지표 나란히 보기"),
    ("views/portfolio.py", ":material/account_balance_wallet:", "포트폴리오", "수익률, 비중, 쏠림·악재 점검"),
    ("views/signals.py", ":material/candlestick_chart:", "매매 참고 구간", "지지·저항 구간과 전략 백테스트"),
]


def delta_text(pct):
    if pct is None:
        return None
    return f"{pct:+.2f}%"


def delta_color(pct):
    # 한국 시장 관례: 오르면 빨강, 내리면 파랑
    if pct is None or pct == 0:
        return "off"
    return "red" if pct > 0 else "blue"


def price_text(value, unit=""):
    if value >= 1000:
        return f"{value:,.0f}{unit}" if unit == "원" and value >= 10000 else f"{value:,.2f}{unit}"
    return f"{value:,.2f}{unit}"


index = company_index()
names_by_ticker = {t: n for n, (t, _s) in index.items()}
options = search_options()
store, portfolio = ui.get_store(), ui.get_portfolio()
holdings = portfolio.holdings()

# 주요 종목: 보유 종목 먼저, 나머지는 미국 대표 종목으로 채움 (티커 목록)
stock_tickers = [h.ticker for h in holdings]
stock_tickers += [t for t in DEFAULT_STOCKS if t not in stock_tickers]
stock_tickers = stock_tickers[:MAX_STOCKS]
held_by_ticker = {h.ticker: h for h in holdings}
tickers = tuple(dict.fromkeys([t for _, t, _ in INDICES] + stock_tickers + [h.ticker for h in holdings]))

now = datetime.now(ui.KST)
st.title("대지니")
st.caption(f"{now.month}월 {now.day}일 ({WEEKDAYS[now.weekday()]}) {now:%H:%M} · 시세는 10분마다 갱신(실시간 아님) · "
           "참고용 정보이며 매수·매도 권유가 아니에요")

with st.spinner("시세를 불러오는 중"):
    try:
        quotes = ui.board(tickers)
    except Exception as e:
        quotes = {}
        st.warning(f"시세를 불러오지 못했어요: {e}")

# 시장 지수
cols = st.columns(len(INDICES))
for col, (label, ticker, unit) in zip(cols, INDICES):
    q = quotes.get(ticker)
    if not q:
        col.metric(label, "—", border=True)
        continue
    col.metric(label, price_text(q["price"], unit), delta_text(q["change_pct"]),
               delta_color=delta_color(q["change_pct"]), chart_data=q["closes"], chart_type="area", border=True)

# 오늘의 시장 뉴스 + 내 포트폴리오
news_col, side_col = st.columns([2, 1], gap="medium")
with news_col.container(border=True, height="stretch"):
    st.subheader(":material/bolt: 오늘의 미국 증시 뉴스", anchor=False)
    with st.spinner("최신 뉴스를 확인하는 중"):
        try:
            result = ui.refresh_market_news()
            if result.error:
                st.caption(result.error)
        except Exception as e:
            st.caption(f"뉴스를 가져오지 못했어요: {e}")
    summary, articles = market_news(store)
    if summary and summary["lines"]:
        st.markdown("\n".join(f"{i}. {ui.md(line)}" for i, line in enumerate(summary["lines"], 1)))
        st.caption(f"최근 하루 미국 증시 기사를 AI가 요약 · {ui.kst(summary['created_at'])}")
    elif articles:
        st.markdown("\n".join(f"- {ui.md(a['title'])}" for a in articles[:3]))
        st.caption("AI 3줄 요약을 보려면 .env에 ANTHROPIC_API_KEY를 넣으세요. 지금은 최신 헤드라인을 보여드려요.")
    else:
        st.caption("최근 하루 미국 증시 기사를 찾지 못했어요.")
    if articles:
        with st.expander("관련 기사"):
            for a in articles[:5]:
                link = f"[{ui.md(a['title'])}]({a['url']})" if a["url"].startswith("https://") else ui.md(a["title"])
                st.markdown(f"{link}  \n:gray[{ui.md(a['source'] or '')} · {ui.kst(a['published'])}]")
    if st.button("내 관심 키워드 뉴스 보기", icon=":material/arrow_forward:", type="tertiary"):
        st.switch_page("views/news.py")

with side_col.container(border=True, height="stretch"):
    st.subheader(":material/account_balance_wallet: 내 포트폴리오", anchor=False)
    if holdings:
        held = {h.ticker: (quotes[h.ticker]["price"], quotes[h.ticker]["prev"]) for h in holdings if h.ticker in quotes}
        fx = quotes.get("KRW=X", {}).get("price")
        _positions, s = evaluate(holdings, held, fx)
        st.metric("총 평가금액", fmt_krw(s.value), delta_text(s.pnl_pct),
                  delta_color=delta_color(s.pnl_pct), delta_description="투자 원금 대비")
        st.metric("오늘 변동", fmt_krw(s.day_change), delta_text(s.day_pct),
                  delta_color=delta_color(s.day_pct), delta_description="전일 종가 대비")
        st.caption(f"보유 종목 {len(holdings)}개")
    else:
        st.write("보유 종목을 등록하면 수익률과 오늘 변동을 여기서 바로 볼 수 있어요.")
    if st.button("포트폴리오 열기", icon=":material/arrow_forward:", type="tertiary"):
        st.switch_page("views/portfolio.py")

# 주요 종목
st.subheader("주요 종목", anchor=False)
st.caption("보유 종목이 먼저 나와요. 종목 이름을 누르면 기업 분석으로 이동해요(ETF 제외).")
per_row = 4
for row_start in range(0, len(stock_tickers), per_row):
    row = st.columns(per_row)
    for col, ticker in zip(row, stock_tickers[row_start:row_start + per_row]):
        name = names_by_ticker.get(ticker) or (held_by_ticker[ticker].name if ticker in held_by_ticker else ticker)
        sector = options.get(ticker, ("", held_by_ticker[ticker].sector if ticker in held_by_ticker else ""))[1]
        q = quotes.get(ticker)
        with col.container(border=True):
            if ticker in names_by_ticker:
                if st.button(name, key=f"open-{ticker}", type="tertiary", icon=":material/open_in_new:"):
                    st.session_state["company"] = name
                    st.switch_page("views/company.py")
            else:
                st.markdown(f"**{ui.md(name)}**")
            label = f"{ticker} · {sector}" + (" · 보유" if ticker in held_by_ticker else "")
            if q:
                st.metric(label, ui.dollars(fmt_price(q["price"], currency_of(ticker))), delta_text(q["change_pct"]),
                          delta_color=delta_color(q["change_pct"]), chart_data=q["closes"], chart_type="line")
            else:
                st.caption("시세를 불러오지 못했어요")

# 바로가기
st.subheader("더 알아보기", anchor=False)
cols = st.columns(len(SHORTCUTS))
for col, (page, icon, title, desc) in zip(cols, SHORTCUTS):
    with col.container(border=True, height="stretch"):
        st.markdown(f"**{icon} {title}**")
        st.caption(desc)
        if st.button("열기", key=f"go-{page}", use_container_width=True):
            st.switch_page(page)
