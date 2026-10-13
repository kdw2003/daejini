"""기업 분석: 핵심 지표, 주가 흐름, 연간 실적, 뉴스, 공시, AI 브리핑."""
import altair as alt
import pandas as pd
import streamlit as st

from daejini import ui
from daejini.company import dart, sec
from daejini.company.analyze import brief
from daejini.company.data import company_index
from daejini.company.metrics import METRIC_INFO, fmt_metric, fmt_money, fmt_price
from daejini.news.analyze import AnalysisError
from daejini.news.service import api_error_message, refresh_keyword, since_iso

BADGE = {"호재": ":red-badge[호재]", "악재": ":blue-badge[악재]", "중립": ":gray-badge[중립]", None: ":gray-badge[분석 전]"}


@st.cache_data(ttl=3600, show_spinner=False)
def disclosures(ticker: str, key: str):
    return dart.recent_disclosures(ticker, key)


@st.cache_data(ttl=3600, show_spinner=False)
def sec_filings(ticker: str):
    return sec.recent_filings(ticker)


def compare_text(key, value, avg):
    if value is None or avg is None:
        return ""
    value, avg = round(value, 1), round(avg, 1)  # 화면에 보이는 자릿수로 비교
    return "중간값보다 높음" if value > avg else "중간값보다 낮음" if value < avg else "중간값과 같음"


index = company_index()
name = st.selectbox("기업", list(index), format_func=lambda n: f"{n} · {index[n][1]}", key="company")
ticker, sector = index[name]

with st.spinner(f"{name}와 {sector} 업종 데이터를 불러오는 중"):
    snap = ui.snapshot(name)
    peers = ui.sector_snapshots(sector)
if snap.error:
    st.error(snap.error)
    st.stop()
avg = ui.sector_average(peers)
latest = snap.annuals[0] if snap.annuals else None
cur = snap.currency
big_unit, big_div = ("조 원", 1e12) if cur == "KRW" else ("억 달러", 1e8)

# 머리글
st.title(name)
st.caption(f"{ticker} · {sector} · 시세와 재무 데이터: Yahoo Finance")
top = st.columns(3)
top[0].metric("현재가", ui.dollars(fmt_price(snap.price, cur)))
top[1].metric("시가총액", ui.dollars(fmt_money(snap.market_cap, cur)))
if snap.year_low and snap.year_high:
    top[2].metric("52주 범위", ui.dollars(f"{fmt_price(snap.year_low, cur)} ~ {fmt_price(snap.year_high, cur)}"))

# 핵심 지표
st.subheader("핵심 지표")
if latest:
    st.caption(f"현재 시가총액 ÷ {latest.year}년 연간 실적(지배주주 기준). 업종 중간값은 {sector} {len(peers)}개 기업의 중간값이에요.")
cols = st.columns(len(METRIC_INFO))
for col, (key, (label, _unit, _higher, desc)) in zip(cols, METRIC_INFO.items()):
    value = getattr(snap.metrics, key)
    col.metric(label, fmt_metric(key, value, snap.metrics.loss), help=desc)
    col.caption(f"업종 중간값 {fmt_metric(key, avg[key])}  \n{compare_text(key, value, avg[key])}")

left, right = st.columns(2)

# 주가 흐름
with left:
    st.subheader("주가 흐름 (1년)")
    try:
        hist = ui.history(ticker)
    except Exception as e:
        hist = None
        st.warning(f"주가를 불러오지 못했어요: {e}")
    if hist is not None and not hist.empty:
        hist = hist[hist["date"] >= hist["date"].max() - pd.Timedelta(days=365)]
        long = hist.melt("date", ["close", "ma20", "ma60"], var_name="series", value_name="price").dropna()
        long["series"] = long["series"].map({"close": "종가", "ma20": "20일 이동평균", "ma60": "60일 이동평균"})
        chart = (
            alt.Chart(long)
            .mark_line(strokeWidth=2, strokeCap="round")
            .encode(
                x=alt.X("date:T", title=None, axis=alt.Axis(format="%y.%m")),
                y=alt.Y("price:Q", title="원" if cur == "KRW" else "달러", scale=alt.Scale(zero=False),
                        axis=alt.Axis(format=",.0f" if cur == "KRW" else "$,.0f")),
                color=alt.Color("series:N", title=None,
                                scale=alt.Scale(domain=["종가", "20일 이동평균", "60일 이동평균"],
                                                range=["#1f5fd1", "#e8833a", "#9aa3ad"]),
                                legend=alt.Legend(orient="top")),
                tooltip=[alt.Tooltip("date:T", title="날짜", format="%Y-%m-%d"),
                         alt.Tooltip("series:N", title="구분"),
                         alt.Tooltip("price:Q", title="가격", format=",.0f" if cur == "KRW" else "$,.2f")],
            )
            .properties(height=300)
        )
        st.altair_chart(chart, use_container_width=True)

# 연간 실적
with right:
    st.subheader("연간 실적")
    if snap.annuals:
        rows = []
        for a in reversed(snap.annuals):
            for label, v in (("매출", a.revenue), ("영업이익", a.operating_income), ("순이익", a.net_income)):
                if v is not None:
                    rows.append({"연도": str(a.year), "항목": label, "금액": v / big_div})
        chart = (
            alt.Chart(pd.DataFrame(rows))
            .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
            .encode(
                x=alt.X("연도:N", title=None, axis=alt.Axis(labelAngle=0)),
                xOffset=alt.XOffset("항목:N", sort=["매출", "영업이익", "순이익"]),
                y=alt.Y("금액:Q", title=big_unit, axis=alt.Axis(format=",.0f")),
                color=alt.Color("항목:N", title=None, sort=["매출", "영업이익", "순이익"],
                                scale=alt.Scale(range=["#9aa3ad", "#1f5fd1", "#e8833a"]),
                                legend=alt.Legend(orient="top")),
                tooltip=["연도", "항목", alt.Tooltip("금액:Q", title=big_unit, format=",.1f")],
            )
            .properties(height=300)
        )
        st.altair_chart(chart, use_container_width=True)
        table = pd.DataFrame([{
            "연도": a.year,
            "매출": fmt_money(a.revenue, cur),
            "영업이익": fmt_money(a.operating_income, cur),
            "순이익": fmt_money(a.net_income, cur),
            "영업이익률": fmt_metric("operating_margin",
                                 a.operating_income / a.revenue * 100 if a.operating_income is not None and a.revenue else None),
        } for a in snap.annuals])
        st.dataframe(table, hide_index=True, use_container_width=True)
    else:
        st.caption("연간 실적 데이터가 없어요.")

news_col, dart_col = st.columns(2)

# 최근 뉴스 (뉴스 브리핑과 연결)
with news_col:
    st.subheader("최근 뉴스")
    store, client = ui.get_store(), ui.get_client()
    if name not in store.keywords():
        st.caption(f"'{name}'은(는) 아직 관심 키워드가 아니에요.")
        if st.button("관심 키워드에 추가하고 뉴스 모으기"):
            store.add_keyword(name)
            with st.spinner("뉴스를 모으는 중"):
                result = refresh_keyword(store, name, client, days=7)
            if result.error:
                st.warning(result.error)
            st.rerun()
        news = []
    else:
        news = store.recent_articles(name, since_iso(7))
        if not news:
            st.caption("최근 7일 기사가 없어요. 뉴스 브리핑에서 새로고침해 보세요.")
        for a in news[:6]:
            link = f"[{ui.md(a['title'])}]({a['url']})" if a["url"].startswith("https://") else ui.md(a["title"])
            st.markdown(f"{BADGE[a['sentiment']]} {link}")
            st.caption(f"{ui.md(a['source'] or '')} · {ui.kst(a['published'])}")

# 공시: 미국 종목은 SEC, 한국 종목은 DART
with dart_col:
    if cur == "USD":
        st.subheader("최근 공시 (SEC, 180일)")
        try:
            items, insider = sec_filings(ticker)
        except Exception as e:
            items, insider = None, 0
            st.warning(f"SEC 공시를 불러오지 못했어요: {e}")
        if items == []:
            st.caption("최근 180일 주요 공시가 없어요.")
        for d in items or []:
            st.markdown(f"[{d['title']}]({d['url']}) :gray[{d['form']}]")
            st.caption(d["date"])
        if insider:
            st.caption(f"같은 기간 임원·대주주 내부자 거래 신고(Form 4) {insider}건")
    else:
        st.subheader("최근 공시 (DART, 90일)")
        key = dart.api_key()
        if not key:
            st.info("공시를 보려면 opendart.fss.or.kr에서 무료 API 키를 받아 .env의 DART_API_KEY에 넣으세요.")
        else:
            try:
                items = disclosures(ticker, key)
            except Exception as e:
                items = None
                st.warning(f"공시를 불러오지 못했어요: {e}")
            if items == []:
                st.caption("최근 90일 공시가 없어요.")
            for d in items or []:
                st.markdown(f"[{ui.md(d['title'])}]({d['url']})")
                st.caption(f"{d['date']} · {ui.md(d['filer'])}")

# AI 브리핑
st.subheader("AI 브리핑")
client = ui.get_client()
if client is None:
    st.info("AI 브리핑을 쓰려면 .env에 ANTHROPIC_API_KEY를 넣으세요.")
else:
    state_key = f"brief-{name}"
    if st.button("지표와 뉴스로 브리핑 만들기", type="primary"):
        with st.spinner("분석 중 (30초 안팎 걸려요)"):
            try:
                st.session_state[state_key] = brief(client, snap, avg, news)
            except AnalysisError as e:
                st.warning(str(e))
            except Exception as e:
                st.warning(api_error_message(e))
    result = st.session_state.get(state_key)
    if result:
        st.markdown(f"**{ui.md(result.headline)}**")
        cols = st.columns(3)
        for col, title, items in zip(cols, ("강점", "약점·위험", "체크포인트"),
                                     (result.strengths, result.weaknesses, result.checkpoints)):
            col.markdown(f"**{title}**")
            col.markdown("\n".join(f"- {ui.md(x)}" for x in items))
        st.caption("지표와 기사 제목을 바탕으로 한 AI 의견이에요. 매수·매도 권유가 아니에요.")
