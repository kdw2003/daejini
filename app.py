"""대지니 투자 비서 (Streamlit). 실행: streamlit run app.py"""
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(page_title="대지니", page_icon=":material/insights:", layout="wide")

page = st.navigation(
    [
        st.Page("views/home.py", title="홈", icon=":material/home:", default=True),
        st.Page("views/news.py", title="뉴스 브리핑", icon=":material/newspaper:"),
        st.Page("views/company.py", title="기업 분석", icon=":material/domain:"),
        st.Page("views/sector.py", title="산업 비교", icon=":material/compare_arrows:"),
        st.Page("views/portfolio.py", title="포트폴리오", icon=":material/account_balance_wallet:"),
        st.Page("views/signals.py", title="매매 참고 구간", icon=":material/candlestick_chart:"),
    ],
    position="top",
)
page.run()
