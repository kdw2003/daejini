"""포트폴리오: 검색해서 바로 추가, 보유 종목 카드, 비중·수익률, 점검, 백업·복원."""
import json
from datetime import datetime

import altair as alt
import pandas as pd
import streamlit as st

from daejini import ui
from daejini.company.data import resolve_query, search_options
from daejini.company.metrics import fmt_krw, fmt_money, fmt_price
from daejini.news.service import refresh_keyword, since_iso
from daejini.portfolio.valuation import check, evaluate, sector_weights

UP, DOWN = "#d1242f", "#1d5fd0"  # 한국 시장 관례: 상승 빨강, 하락 파랑
CATEGORY = ["#2a9d8f", "#e9c46a", "#8e7cc3", "#f4a261", "#6b9080", "#b5838d", "#a3b18a", "#9c755f"]
EXAMPLE = [("NVDA", 5, 0.85), ("AAPL", 10, 0.95), ("MSFT", 4, 1.05), ("QQQ", 3, 0.92), ("TSLA", 6, 1.12)]


def signed(value, unit="%", digits=2):
    """오르면 빨강 ▲, 내리면 파랑 ▼ (마크다운)."""
    if value is None:
        return "—"
    if round(value, digits) == 0:
        return f"0{unit}"
    if value > 0:
        return f":red[▲ {value:,.{digits}f}{unit}]"
    if value < 0:
        return f":blue[▼ {abs(value):,.{digits}f}{unit}]"
    return f"0{unit}"


def delta_color(value):
    if value is None or round(value, 2) == 0:
        return "off"
    return "red" if value > 0 else "blue"


def qty_text(q):
    return f"{q:,.0f}" if float(q).is_integer() else f"{q:,.4f}".rstrip("0").rstrip(".")


def backup_section(expanded: bool):
    with st.expander("백업 · 복원", icon=":material/save:", expanded=expanded):
        st.caption("클라우드에 올린 앱은 서버가 다시 시작되면 저장된 데이터가 지워질 수 있어요. "
                   "종목을 바꾼 뒤에는 백업 파일을 받아 두세요.")
        b_col, r_col = st.columns(2)
        b_col.download_button(
            "백업 파일 받기", data=json.dumps(portfolio.export(), ensure_ascii=False, indent=2),
            file_name=f"daejini-portfolio-{datetime.now():%Y%m%d}.json", mime="application/json",
            icon=":material/download:", use_container_width=True, disabled=not holdings,
        )
        upload = r_col.file_uploader("백업 파일로 복원", type=["json"], label_visibility="collapsed")
        if upload is not None and r_col.button("이 파일로 복원 (지금 종목을 대체해요)", use_container_width=True):
            try:
                data = json.loads(upload.getvalue().decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                st.error("JSON 파일을 읽지 못했어요.")
                return
            try:
                count = portfolio.restore(data)
            except ValueError as e:
                st.error(str(e))
                return
            st.toast(f"보유 종목 {count}개를 복원했어요.")
            st.rerun()


options = search_options()
portfolio, news_store, client = ui.get_portfolio(), ui.get_store(), ui.get_client()
holdings = portfolio.holdings()
fx = ui.usd_krw()

st.title("포트폴리오")
st.caption("시세·환율: Yahoo Finance(10분마다 갱신, 실시간 아님). 달러 종목은 현재 환율로 원화 환산하며, 매수 당시 환율에 따른 손익은 포함하지 않아요.")

# ── 종목 추가: 검색 → 수량 → 평균단가(현재가로 미리 채움) → 추가
with st.container(border=True):
    st.markdown("**:material/add_circle: 종목 추가**")
    c_pick, c_qty, c_price, c_btn = st.columns([3, 1.2, 1.5, 1], vertical_alignment="bottom")
    pick = c_pick.selectbox(
        "종목 검색", list(options), index=None, accept_new_options=True, key="add-pick",
        placeholder="이름이나 티커 입력 (예: 엔비디아, NVDA, SPY, 005930)",
        format_func=lambda t: f"{options[t][0]} · {t}" if t in options else t,
    )
    info = None
    if pick:
        for candidate in resolve_query(pick, options):
            info = ui.lookup(candidate)
            if info:
                break
    currency = info["currency"] if info else "USD"
    unit = "원" if currency == "KRW" else "$"
    qty = c_qty.number_input("수량(주)", min_value=0.0001, value=1.0, step=1.0, key="add-qty",
                             help="미국 주식은 소수점 수량도 넣을 수 있어요.")
    price = c_price.number_input(
        f"평균단가({unit})", min_value=0.01, step=1.0 if currency == "USD" else 100.0,
        value=float(round(info["price"], 2)) if info else None, key=f"add-price-{info['ticker'] if info else 'none'}",
        help="처음에는 현재가로 채워져요. 실제로 산 가격으로 바꾸세요.",
    )
    add = c_btn.button("추가", type="primary", use_container_width=True, disabled=not (info and price))

    if pick and not info:
        st.error(f"'{pick}' 시세를 찾지 못했어요. 미국 종목은 티커(예: NVDA), 한국 종목은 6자리 코드(예: 005930)로 입력하세요.")
    elif info:
        ticker = info["ticker"]
        name, sector = options.get(ticker, (info["name"], "ETF" if info["is_etf"] else "기타"))
        cost = qty * (price or 0)
        line = f"**{ui.md(name)}** ({ticker}) 현재가 {fmt_price(info['price'], currency)}"
        if price:
            line += f" · 매수금액 {fmt_money(cost, currency)}"
            if currency == "USD" and fx:
                line += f" (약 {fmt_krw(cost * fx)})"
            line += f" · 지금 기준 수익률 {signed((info['price'] / price - 1) * 100)}"
        st.markdown(ui.dollars(line))
        held = next((h for h in holdings if h.ticker == ticker), None)
        if held and price:
            new_avg = (held.cost + cost) / (held.quantity + qty)
            st.caption(ui.dollars(f"이미 {qty_text(held.quantity)}주 보유 중이에요. 추가하면 {qty_text(held.quantity + qty)}주, "
                                  f"평균단가 {fmt_price(new_avg, currency)}로 바뀌어요."))
        if add:
            h = portfolio.buy(ticker, name, sector, qty, price)
            st.toast(ui.dollars(f"{h.name} {qty_text(h.quantity)}주 · 평균단가 {fmt_price(h.avg_price, currency)}로 저장했어요."))
            for k in ("add-pick", "add-qty"):
                st.session_state.pop(k, None)
            st.rerun()

if not holdings:
    st.write("보유 종목을 추가하면 수익률, 비중, 쏠림 점검, 악재 뉴스 알림을 보여드려요.")
    if st.button("예시 포트폴리오로 체험하기", icon=":material/science:"):
        for ticker, q, factor in EXAMPLE:
            info = ui.lookup(ticker)
            if info:
                name, sector = options.get(ticker, (ticker, "기타"))
                portfolio.buy(ticker, name, sector, q, round(info["price"] * factor, 2))
        st.session_state["example-loaded"] = True
        st.rerun()
    backup_section(expanded=True)
    st.stop()

if st.session_state.get("example-loaded"):
    st.info("예시 종목을 넣었어요. 평균단가는 현재가로 만든 가상 값이에요. 각 종목 카드의 :material/edit: 버튼에서 고치거나 지울 수 있어요.")

with st.spinner("시세를 불러오는 중"):
    quotes = {}
    for h in holdings:
        q = ui.lookup(h.ticker)
        if q:
            quotes[h.ticker] = (q["price"], q["prev"])
positions, summary = evaluate(holdings, quotes, fx)
if summary.missing_prices:
    st.warning(f"시세나 환율을 불러오지 못해 평가에서 뺀 종목: {', '.join(summary.missing_prices)}")

# ── 요약
cols = st.columns(4)
cols[0].metric("총 평가금액", fmt_krw(summary.value), border=True,
               delta=ui.dollars(f"약 ${summary.value_usd:,.0f}") if summary.value_usd else None, delta_color="off", delta_arrow="off")
cols[1].metric("총 손익", fmt_krw(summary.pnl), border=True,
               delta=f"{summary.pnl_pct:+.2f}%" if summary.pnl_pct is not None else None, delta_color=delta_color(summary.pnl_pct))
cols[2].metric("오늘 변동", fmt_krw(summary.day_change), border=True,
               delta=f"{summary.day_pct:+.2f}%" if summary.day_pct is not None else None, delta_color=delta_color(summary.day_pct))
cols[3].metric("원/달러 환율", f"{fx:,.2f}원" if fx else "—", border=True,
               delta=f"투자 원금 {fmt_krw(summary.cost)}", delta_color="off", delta_arrow="off")

# ── 점검
names = [h.name for h in holdings]
tracked = set(news_store.keywords())
news_by_name = {n: news_store.recent_articles(n, since_iso(3)) for n in names if n in tracked}
alerts = check(positions, news_by_name)
warnings = [a for a in alerts if a.level == "warning"]
label = f"점검 결과 · 주의 {len(warnings)}건, 참고 {len(alerts) - len(warnings)}건" if alerts else "점검 결과 · 눈에 띄는 문제 없음"
with st.expander(label, icon=":material/fact_check:", expanded=bool(warnings)):
    for a in alerts:
        (st.warning if a.level == "warning" else st.info)(ui.md(a.message))
    if not alerts:
        st.success("쏠림, 손실 구간, 악재 뉴스 중 눈에 띄는 것이 없어요.")
    news_col, note_col = st.columns([1, 3], vertical_alignment="center")
    if news_col.button("보유 종목 뉴스 확인", icon=":material/newspaper:"):
        with st.spinner("보유 종목 뉴스를 모으고 분석하는 중"):
            errors = []
            for n in names:
                news_store.add_keyword(n)
                r = refresh_keyword(news_store, n, client, days=3)
                if r.error:
                    errors.append(f"{n}: {r.error}")
        for e in errors:
            st.warning(e)
        st.rerun()
    note = "최근 3일 뉴스에서 악재를 찾아요. 보유 종목은 뉴스 브리핑 관심 키워드에도 추가돼요."
    if client is None:
        note += " 악재 판별에는 Claude API 키가 필요해요."
    note_col.caption(note)

# ── 보유 종목 카드 (평가금액 큰 순)
st.subheader("보유 종목", anchor=False)
for p in sorted(positions, key=lambda p: p.value_krw or 0, reverse=True):
    cur = p.currency
    with st.container(border=True):
        c_name, c_price, c_value, c_ret, c_edit = st.columns([2.4, 1.6, 1.8, 1.6, 0.5], vertical_alignment="center")
        c_name.markdown(ui.dollars(f"**{ui.md(p.name)}**  \n:gray[{p.ticker} · {qty_text(p.quantity)}주 · 평단 {fmt_price(p.avg_price, cur)}]"))
        if p.value is None:
            c_price.caption("시세 없음")
        else:
            c_price.markdown(ui.dollars(f":gray[현재가]  \n**{fmt_price(p.price, cur)}** {signed(p.day_pct)}"))
            value_line = f":gray[평가금액]  \n**{fmt_money(p.value, cur)}**"
            if cur == "USD":
                value_line += f" :gray[≈ {fmt_krw(p.value_krw)}]"
            c_value.markdown(ui.dollars(value_line))
            c_ret.markdown(ui.dollars(f":gray[수익률]  \n**{signed(p.pnl_pct)}**  \n:gray[{'+' if p.pnl >= 0 else ''}{fmt_money(p.pnl, cur)}]"))
        with c_edit.popover("", icon=":material/edit:", help="수량·평균단가 수정, 삭제"):
            st.markdown(f"**{ui.md(p.name)}** 수정")
            new_qty = st.number_input("수량(주)", min_value=0.0001, value=float(p.quantity), step=1.0, key=f"q-{p.ticker}")
            new_avg = st.number_input(f"평균단가({'원' if cur == 'KRW' else '$'})", min_value=0.01,
                                      value=float(p.avg_price), step=1.0, key=f"a-{p.ticker}")
            s_col, d_col = st.columns(2)
            if s_col.button("저장", key=f"save-{p.ticker}", type="primary", use_container_width=True):
                portfolio.update(p.ticker, new_qty, new_avg)
                st.session_state.pop("example-loaded", None)
                st.rerun()
            if d_col.button("삭제", key=f"del-{p.ticker}", use_container_width=True):
                portfolio.remove(p.ticker)
                st.session_state.pop("example-loaded", None)
                st.rerun()
        if p.weight is not None:
            st.progress(min(p.weight / 100, 1.0), text=f"비중 {p.weight:.1f}%")

# ── 비중과 수익률 차트
valued = [p for p in positions if p.weight is not None]
if valued:
    st.subheader("한눈에 보기", anchor=False)

    def donut(df):
        return (
            alt.Chart(df)
            .mark_arc(innerRadius=60, stroke="white", strokeWidth=2)
            .encode(theta="비중:Q", color=alt.Color("이름:N", title=None, sort=df["이름"].tolist(), scale=alt.Scale(range=CATEGORY)),
                    tooltip=["이름", alt.Tooltip("비중:Q", format=".1f", title="비중(%)")])
            .properties(height=280)
        )

    t_stock, t_sector, t_return = st.tabs(["종목별 비중", "업종별 비중", "종목별 수익률"])
    with t_stock:
        st.altair_chart(donut(pd.DataFrame([{"이름": p.name, "비중": p.weight} for p in valued])),
                        use_container_width=True, theme=None)
    with t_sector:
        st.altair_chart(donut(pd.DataFrame([{"이름": s, "비중": w} for s, w in sector_weights(valued).items()])),
                        use_container_width=True, theme=None)
    with t_return:
        returns = pd.DataFrame([{"종목": p.name, "수익률": p.pnl_pct} for p in valued])
        st.altair_chart(
            alt.Chart(returns)
            .mark_bar(cornerRadiusEnd=4, height=20)
            .encode(y=alt.Y("종목:N", sort="-x", title=None), x=alt.X("수익률:Q", title="수익률(%)"),
                    color=alt.condition("datum.수익률 >= 0", alt.value(UP), alt.value(DOWN)),
                    tooltip=["종목", alt.Tooltip("수익률:Q", format="+.2f")])
            .properties(height=60 + 36 * len(valued)),
            use_container_width=True,
        )

backup_section(expanded=False)

with st.expander("포트폴리오 전체 삭제", icon=":material/delete:"):
    confirm = st.checkbox("모든 보유 종목을 지울게요. 되돌릴 수 없어요.")
    if st.button("전체 삭제", disabled=not confirm):
        for h in holdings:
            portfolio.remove(h.ticker)
        st.session_state.pop("example-loaded", None)
        st.rerun()
