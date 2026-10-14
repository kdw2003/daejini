"""홈: 총 자산 → 메뉴 아이콘 → 보유 주식(매수가·현재가·변동률·그래프) → 미국 증시 뉴스 3줄 요약."""
from datetime import datetime

import streamlit as st

from daejini import ui
from daejini.company.data import company_index
from daejini.company.metrics import fmt_krw, fmt_money, fmt_price
from daejini.news.market import market_news
from daejini.portfolio.valuation import evaluate

WEEKDAYS = "월화수목금토일"
MENU = [
    ("views/news.py", ":material/newspaper:", "뉴스"),
    ("views/company.py", ":material/domain:", "기업 분석"),
    ("views/sector.py", ":material/compare_arrows:", "산업 비교"),
    ("views/portfolio.py", ":material/account_balance_wallet:", "포트폴리오"),
    ("views/signals.py", ":material/candlestick_chart:", "매매 구간"),
]
CARDS_PER_ROW = 3

# 메뉴를 앱 아이콘처럼: 아이콘 위, 글자 아래인 둥근 타일. 휴대폰에서도 5개가 한 줄에 들어가게
st.html("""
<style>
.st-key-menu [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; gap: 0.5rem !important; }
.st-key-menu [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] { flex: 1 1 0 !important; min-width: 0 !important; }
.st-key-menu [data-testid="stElementContainer"], .st-key-menu [data-testid="stPageLink"] { width: 100% !important; }
.st-key-menu [data-testid="stPageLink"] a {
  display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 0.35rem;
  padding: 0.9rem 0.2rem; border: 1px solid #e3e8ec; border-radius: 16px; background: #f3f6f8;
  text-decoration: none; height: 100%; width: 100%; box-sizing: border-box;
}
.st-key-menu [data-testid="stPageLink"] a:hover { background: #e6f0f3; border-color: #1f6f8b; }
.st-key-menu [data-testid="stPageLink"] a [data-testid="stIconMaterial"] { font-size: 2rem !important; color: #1f6f8b; }
.st-key-menu [data-testid="stPageLink"] a p { font-size: 0.85rem; text-align: center; margin: 0; white-space: nowrap; }
@media (max-width: 640px) {
  /* 휴대폰: 보유 주식 카드는 한 줄에 하나씩 (글자가 잘리지 않게) */
  .st-key-holdings [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] { flex: 1 1 100% !important; min-width: 100% !important; }
  .st-key-menu [data-testid="stPageLink"] a { padding: 0.7rem 0.1rem; border-radius: 14px; }
  .st-key-menu [data-testid="stPageLink"] a [data-testid="stIconMaterial"] { font-size: 1.6rem !important; }
  .st-key-menu [data-testid="stPageLink"] a p { font-size: 0.72rem; }
}
</style>
""")


def delta_text(pct):
    if pct is None:
        return None
    if round(pct, 2) == 0:
        return "0.00%"  # 아주 작은 소수점 차이로 +0.00%·-0.00%가 나오지 않게
    return f"{pct:+.2f}%"


def delta_color(pct):
    # 한국 시장 관례: 오르면 빨강, 내리면 파랑
    if pct is None or round(pct, 2) == 0:
        return "off"
    return "red" if pct > 0 else "blue"


def colored(amount, pct):
    """금액과 등락률을 한국식 색으로: 오르면 빨강, 내리면 파랑."""
    sign = "+" if amount > 0 else ""
    text = f"**{sign}{fmt_krw(amount)}** {delta_text(pct) or ''}".strip()
    color = delta_color(pct)
    return text if color == "off" else f":{color}[{text}]"


def qty_text(q):
    return f"{q:,.0f}" if float(q).is_integer() else f"{q:,.4f}".rstrip("0").rstrip(".")


index = company_index()
names_by_ticker = {t: n for n, (t, _s) in index.items()}
store, portfolio = ui.get_store(), ui.get_portfolio()
holdings = portfolio.holdings()

now = datetime.now(ui.KST)
st.title("대지니")
st.caption(f"{now.month}월 {now.day}일 ({WEEKDAYS[now.weekday()]}) {now:%H:%M} · 시세는 10분마다 갱신(실시간 아님) · "
           "참고용 정보이며 매수·매도 권유가 아니에요")

quotes = {}
if holdings:
    with st.spinner("시세를 불러오는 중"):
        try:
            quotes = ui.board(tuple(dict.fromkeys([h.ticker for h in holdings] + ["KRW=X"])))
        except Exception as e:
            st.warning(f"시세를 불러오지 못했어요: {e}")
fx = quotes.get("KRW=X", {}).get("price")
positions, summary = evaluate(holdings, {t: (q["price"], q["prev"]) for t, q in quotes.items()}, fx)

# ── 1. 총 자산
with st.container(border=True):
    if holdings and summary.value:
        left, right = st.columns([1.4, 1], vertical_alignment="center")
        with left:
            st.metric("총 자산", fmt_krw(summary.value), delta_text(summary.pnl_pct),
                      delta_color=delta_color(summary.pnl_pct), delta_description="원금 대비")
            if summary.value_usd:
                st.caption(ui.dollars(f"약 ${summary.value_usd:,.0f} · 원/달러 {fx:,.2f}원 · 보유 종목 {len(holdings)}개"))
        with right:
            st.markdown(f":gray[총 손익]  \n{colored(summary.pnl, summary.pnl_pct)}")
            st.markdown(f":gray[오늘 변동]  \n{colored(summary.day_change, summary.day_pct)}")
        if summary.missing_prices:
            st.caption(f"시세를 못 불러와 빠진 종목: {', '.join(summary.missing_prices)}")
    else:
        st.metric("총 자산", "—")
        st.caption("보유 종목을 등록하면 총 자산, 손익, 오늘 변동이 여기에 보여요.")

# ── 2. 메뉴 아이콘
with st.container(key="menu"):
    cols = st.columns(len(MENU))
    for col, (page, icon, label) in zip(cols, MENU):
        col.page_link(page, label=label, icon=icon)

# ── 3. 보유 주식: 매수가 · 현재가 · 변동률 · 1개월 그래프
st.subheader("내 주식", anchor=False)
if not holdings:
    st.caption("아직 등록한 종목이 없어요.")
    st.page_link("views/portfolio.py", label="포트폴리오에서 종목 추가하기", icon=":material/add_circle:")
else:
    st.caption("변동률은 매수가 대비 수익률이에요. 그래프는 최근 한 달 주가예요.")
    ordered = sorted(positions, key=lambda p: p.value_krw or 0, reverse=True)
    holdings_box = st.container(key="holdings")
    for start in range(0, len(ordered), CARDS_PER_ROW):
        row = holdings_box.columns(CARDS_PER_ROW)
        for col, p in zip(row, ordered[start:start + CARDS_PER_ROW]):
            q = quotes.get(p.ticker, {})
            with col.container(border=True):
                st.markdown(f"**{ui.md(p.name)}** :gray[{p.ticker}]")
                if p.value is None:
                    st.caption("시세를 불러오지 못했어요")
                    continue
                st.metric(
                    ui.dollars(f"매수가 {fmt_price(p.avg_price, p.currency)} → 현재가"),
                    ui.dollars(fmt_price(p.price, p.currency)),
                    delta_text(p.pnl_pct), delta_color=delta_color(p.pnl_pct), delta_description="매수가 대비",
                    chart_data=q.get("closes") or None, chart_type="area",
                )
                today = delta_text(p.day_pct) or "—"
                value = fmt_money(p.value, p.currency) + (f" (약 {fmt_krw(p.value_krw)})" if p.currency == "USD" else "")
                st.caption(ui.dollars(f"{qty_text(p.quantity)}주 · 평가 {value} · 오늘 {today}"))

# ── 4. 아래로 내리면: 미국 증시 뉴스 3줄 요약
st.subheader(":material/bolt: 오늘의 미국 증시 뉴스", anchor=False)
with st.container(border=True):
    with st.spinner("최신 뉴스를 확인하는 중"):
        try:
            result = ui.refresh_market_news()
            if result.error:
                st.caption(result.error)
        except Exception as e:
            st.caption(f"뉴스를 가져오지 못했어요: {e}")
    news_summary, articles = market_news(store)
    if news_summary and news_summary["lines"]:
        st.markdown("\n".join(f"{i}. {ui.md(line)}" for i, line in enumerate(news_summary["lines"], 1)))
        st.caption(f"최근 하루 미국 증시 기사를 AI가 요약 · {ui.kst(news_summary['created_at'])}")
    elif articles:
        st.markdown("\n".join(f"{i}. {ui.md(a['title'])}" for i, a in enumerate(articles[:3], 1)))
        st.caption("AI 3줄 요약은 Claude API 키가 있어야 해요. 지금은 최신 헤드라인 3개를 보여드려요.")
    else:
        st.caption("최근 하루 미국 증시 기사를 찾지 못했어요.")
    if articles:
        with st.expander("관련 기사"):
            for a in articles[:5]:
                link = f"[{ui.md(a['title'])}]({a['url']})" if a["url"].startswith("https://") else ui.md(a["title"])
                st.markdown(f"{link}  \n:gray[{ui.md(a['source'] or '')} · {ui.kst(a['published'])}]")
    st.page_link("views/news.py", label="내 관심 키워드 뉴스 보기", icon=":material/arrow_forward:")
