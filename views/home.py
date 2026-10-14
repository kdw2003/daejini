"""홈: 총 자산 → 메뉴 아이콘 → 보유 주식(매수가·현재가·변동률·그래프) → 미국 증시 뉴스 3줄 요약."""
import base64
import html
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


UP, DOWN, FLAT = "#d1242f", "#1d5fd0", "#8a96a3"  # 한국 시장 관례: 상승 빨강, 하락 파랑


def sparkline(values, color, width=72, height=26):
    """작은 꺾은선 그래프(SVG). 값이 2개 미만이면 빈 칸."""
    vals = [v for v in (values or []) if v is not None]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    step = width / (len(vals) - 1)
    pts = [(i * step, height - 2 - (v - lo) / span * (height - 4)) for i, v in enumerate(vals)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"0,{height} {line} {width},{height}"
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
           f'<polygon points="{area}" fill="{color}" fill-opacity="0.12"/>'
           f'<polyline points="{line}" fill="none" stroke="{color}" stroke-width="1.6" '
           f'stroke-linejoin="round" stroke-linecap="round"/></svg>')
    # st.html은 보안상 <svg> 태그를 지우므로 이미지(data URI)로 넣는다
    data = base64.b64encode(svg.encode()).decode()
    return f'<img src="data:image/svg+xml;base64,{data}" width="{width}" height="{height}" alt="">'



def holdings_table(positions, quotes) -> str:
    """보유 종목을 한 줄씩: 종목 | 매수가 | 현재가 | 변동률 | 그래프."""
    rows = []
    for p in positions:
        name = html.escape(p.name)
        if p.value is None:
            rows.append(f'<div class="dj-row"><div class="dj-name"><b>{name}</b><span>{p.ticker}</span></div>'
                        f'<div class="dj-missing">시세를 불러오지 못했어요</div></div>')
            continue
        pct = p.pnl_pct
        color = FLAT if round(pct, 2) == 0 else (UP if pct > 0 else DOWN)
        value = fmt_money(p.value, p.currency) + (f" (약 {fmt_krw(p.value_krw)})" if p.currency == "USD" else "")
        tip = html.escape(f"{p.name} {qty_text(p.quantity)}주 · 평가 {value} · 오늘 {delta_text(p.day_pct) or '—'}")
        rows.append(
            f'<div class="dj-row" title="{tip}">'
            f'<div class="dj-name"><b>{name}</b><span>{p.ticker}</span></div>'
            f'<div class="dj-num">{fmt_price(p.avg_price, p.currency)}</div>'
            f'<div class="dj-num dj-now">{fmt_price(p.price, p.currency)}</div>'
            f'<div class="dj-pct" style="color:{color}">{delta_text(pct)}</div>'
            f'<div class="dj-chart">{sparkline(quotes.get(p.ticker, {}).get("closes"), color)}</div>'
            f'</div>'
        )
    head = ('<div class="dj-row dj-head"><div class="dj-name">종목</div><div class="dj-num">매수가</div>'
            '<div class="dj-num">현재가</div><div class="dj-pct">변동률</div><div class="dj-chart">1개월</div></div>')
    return f"""
<style>
.dj-list {{ border: 1px solid #e3e8ec; border-radius: 14px; overflow: hidden; font-family: inherit; }}
.dj-row {{ display: grid; grid-template-columns: minmax(0, 1.5fr) minmax(0, 1fr) minmax(0, 1fr) minmax(0, 0.8fr) 76px;
           align-items: center; gap: 8px; padding: 9px 14px; border-top: 1px solid #eef1f4; font-size: 14px; color: #1f2933; }}
.dj-row:first-child {{ border-top: 0; }}
.dj-head {{ background: #f3f6f8; color: #6b7785; font-size: 12px; padding-top: 7px; padding-bottom: 7px; }}
.dj-name {{ min-width: 0; display: flex; flex-direction: column; line-height: 1.25; }}
.dj-name b {{ white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-weight: 600; }}
.dj-name span {{ color: #8a96a3; font-size: 11px; }}
.dj-num, .dj-pct {{ text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; overflow: hidden; text-overflow: ellipsis; }}
.dj-head .dj-name {{ display: block; }}
.dj-now {{ font-weight: 600; }}
.dj-pct {{ font-weight: 600; }}
.dj-chart {{ display: flex; justify-content: flex-end; }}
.dj-missing {{ grid-column: 2 / -1; color: #8a96a3; font-size: 12px; text-align: right; }}
@media (max-width: 640px) {{
  .dj-row {{ grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr) minmax(0, 1fr) minmax(0, 0.85fr) 52px;
             gap: 5px; padding: 8px 10px; font-size: 12px; }}
  .dj-head {{ font-size: 11px; }}
  .dj-name span {{ font-size: 10px; }}
  .dj-chart img {{ width: 52px; height: 22px; }}
}}
</style>
<div class="dj-list">{head}{''.join(rows)}</div>
"""


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
    ordered = sorted(positions, key=lambda p: p.value_krw or 0, reverse=True)
    st.html(holdings_table(ordered, quotes))
    st.caption("변동률은 매수가 대비 수익률, 그래프는 최근 한 달 주가예요. 종목에 손가락(마우스)을 올리면 수량·평가금액이 보여요.")

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
