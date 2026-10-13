"""뉴스 브리핑: 관심 키워드 뉴스 요약과 호재·악재 분류."""
import streamlit as st

from daejini.news.service import refresh_keyword, since_iso
from daejini.ui import get_client, get_store, kst, md

PERIODS = {"오늘·어제": 2, "최근 3일": 3, "최근 7일": 7}
BADGE = {"호재": ":red-badge[호재]", "악재": ":blue-badge[악재]", "중립": ":gray-badge[중립]", None: ":gray-badge[분석 전]"}


def counts(articles):
    c = {"호재": 0, "악재": 0, "중립": 0, None: 0}
    for a in articles:
        c[a["sentiment"]] += 1
    return c


store = get_store()
client = get_client()

# 사이드바: 관심 키워드, 기간, 새로고침
with st.sidebar:
    st.header("관심 키워드")
    with st.form("add-keyword", clear_on_submit=True):
        new_kw = st.text_input("종목, 산업, 경제 주제", placeholder="예: 삼성전자, 2차전지, 기준금리")
        if st.form_submit_button("추가") and new_kw.strip():
            if not store.add_keyword(new_kw):
                st.toast(f"'{new_kw.strip()}'은(는) 이미 있어요")
    for kw in store.keywords():
        name_col, del_col = st.columns([4, 1], vertical_alignment="center")
        name_col.write(kw)
        if del_col.button("✕", key=f"del-{kw}", help=f"'{kw}' 삭제"):
            store.remove_keyword(kw)
            st.rerun()

    st.divider()
    days = PERIODS[st.radio("기간", list(PERIODS), key="period")]
    refresh = st.button("뉴스 새로고침", type="primary", use_container_width=True)
    if client is None:
        st.info("AI 요약과 호재·악재 분류를 쓰려면 .env 파일에 ANTHROPIC_API_KEY를 넣으세요. 지금은 뉴스 수집만 돼요.")

st.title("뉴스 브리핑")
st.caption("AI 분석은 기사 제목만 보고 한 판단이라 틀릴 수 있어요. 매수·매도 권유가 아니니 투자 판단은 직접 하세요.")

keywords = store.keywords()
if not keywords:
    st.write("왼쪽에서 관심 종목이나 산업을 추가한 뒤 **뉴스 새로고침**을 누르세요.")
    st.stop()

if refresh:
    with st.status("뉴스를 모으고 있어요", expanded=False) as status:
        results = []
        for kw in keywords:
            status.update(label=f"'{kw}' 뉴스 수집·분석 중")
            results.append(refresh_keyword(store, kw, client, days=days))
        total = sum(r.new_articles for r in results)
        status.update(label=f"새로고침 완료: 새 기사 {total}건", state="complete")
    for r in results:
        if r.error:
            st.warning(f"{r.keyword}: {r.error}")

data = {kw: store.recent_articles(kw, since_iso(days)) for kw in keywords}

# 한눈에 보기: 키워드별 호재·악재 수와 요약 첫 줄
st.subheader("한눈에 보기")
cols = st.columns(min(len(keywords), 4))
for i, kw in enumerate(keywords):
    c = counts(data[kw])
    summary = store.summary(kw)
    with cols[i % len(cols)].container(border=True):
        st.markdown(f"**{md(kw)}**")
        st.markdown(f":red[호재 {c['호재']}] · :blue[악재 {c['악재']}] · 중립 {c['중립']}"
                    + (f" · 분석 전 {c[None]}" if c[None] else ""))
        if summary and summary["lines"]:
            st.caption(md(summary["lines"][0]))
        elif not data[kw]:
            st.caption("모은 기사가 없어요")

# 키워드별 상세
for tab, kw in zip(st.tabs(keywords), keywords):
    with tab:
        articles = data[kw]
        summary = store.summary(kw)
        if summary:
            st.markdown("**핵심 요약**")
            st.markdown("\n".join(f"- {md(line)}" for line in summary["lines"]))
            st.caption(f"{kst(summary['created_at'])} 분석 · {summary['model']}")
        if not articles:
            st.write("이 기간에 모은 기사가 없어요. **뉴스 새로고침**을 눌러 보세요.")
            continue

        filter_col, sort_col = st.columns([3, 2])
        pick = filter_col.segmented_control(
            "분류", ["전체", "호재", "악재", "중립"], default="전체", key=f"filter-{kw}"
        ) or "전체"
        order = sort_col.segmented_control(
            "정렬", ["최신순", "영향 큰 순"], default="최신순", key=f"order-{kw}"
        ) or "최신순"

        shown = [a for a in articles if pick == "전체" or a["sentiment"] == pick]
        if order == "영향 큰 순":
            shown.sort(key=lambda a: a["impact"] or 0, reverse=True)
        if not shown:
            st.caption(f"'{pick}'로 분류된 기사가 없어요.")

        for a in shown:
            title = md(a["title"])
            link = f"[{title}]({a['url']})" if a["url"].startswith("https://") else title
            st.markdown(f"{BADGE[a['sentiment']]} **{link}**")
            meta = [md(a["source"] or ""), kst(a["published"])]
            if a["impact"]:
                meta.append("영향 " + "●" * a["impact"] + "○" * (3 - a["impact"]))
            if a["target"]:
                meta.append(md(a["target"]))
            st.caption(" · ".join(m for m in meta if m))
            if a["reason"]:
                st.caption(f"근거: {md(a['reason'])}")
