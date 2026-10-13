import io
import json
import zipfile
from types import SimpleNamespace

import pandas as pd
import pytest

from datetime import date

from daejini.company import dart, sec
from daejini.company.analyze import brief, build_prompt
from daejini.company.data import (annuals_from_frames, company_index, load_companies, normalize_ticker,
                                  resolve_query, search_options)
from daejini.company.metrics import (Annual, Metrics, Snapshot, average, compute, median, currency_of, fmt_krw, fmt_metric,
                                     fmt_money, fmt_price)
from daejini.news.analyze import AnalysisError

A2025 = Annual(2025, revenue=300e12, operating_income=45e12, net_income=40e12, equity=400e12, liabilities=100e12)
A2024 = Annual(2024, revenue=250e12, operating_income=30e12, net_income=30e12, equity=370e12, liabilities=95e12)


# 지표 계산
def test_compute_metrics():
    m = compute([A2025, A2024], market_cap=800e12)
    assert m.per == pytest.approx(20)
    assert m.pbr == pytest.approx(2)
    assert m.roe == pytest.approx(10)
    assert m.operating_margin == pytest.approx(15)
    assert m.debt_ratio == pytest.approx(25)
    assert m.revenue_growth == pytest.approx(20)
    assert not m.loss


def test_compute_handles_loss_and_missing_rows():
    loss = Annual(2025, revenue=10e12, operating_income=None, net_income=-1e12, equity=5e12, liabilities=None)
    m = compute([loss], market_cap=20e12)
    assert m.loss and m.per is None and fmt_metric("per", m.per, m.loss) == "적자"
    assert m.operating_margin is None and m.debt_ratio is None and m.revenue_growth is None
    assert compute([], 1e12) == Metrics()


def test_formatting_and_average():
    assert fmt_krw(1.5e15) == "1,500.0조 원"
    assert fmt_krw(5.3e11) == "5,300억 원"
    assert fmt_krw(None) == "—"
    assert fmt_metric("roe", 12.345) == "12.3%"
    assert average([1, None, 3]) == 2 and average([None]) is None
    assert median([30, 31, 151.9, None, 18.9, 27.8]) == 30 and median([1, 2, 3, 10]) == 2.5 and median([]) is None


# yfinance 표 → 연간 실적
def test_annuals_from_frames_prefers_controlling_net_income_and_skips_empty_years():
    cols = [pd.Timestamp("2025-12-31"), pd.Timestamp("2024-12-31"), pd.Timestamp("2021-12-31")]
    income = pd.DataFrame(
        {cols[0]: [300.0, 45.0, 41.0, 40.0], cols[1]: [250.0, 30.0, 31.0, 30.0], cols[2]: [float("nan")] * 4},
        index=["Total Revenue", "Operating Income", "Net Income", "Net Income Common Stockholders"],
    )
    balance = pd.DataFrame({cols[0]: [400.0, 100.0], cols[1]: [370.0, 95.0]},
                           index=["Stockholders Equity", "Total Liabilities Net Minority Interest"])
    annuals = annuals_from_frames(income, balance)
    assert [a.year for a in annuals] == [2025, 2024]
    assert annuals[0].net_income == 40.0 and annuals[0].equity == 400.0


def test_company_list_is_consistent():
    companies = load_companies()
    index = company_index()
    assert sum(len(m) for m in companies.values()) == len(index)  # 기업명 중복 없음
    assert index["엔비디아"] == ("NVDA", "반도체")
    tickers = [t for t, _ in index.values()]
    assert len(set(tickers)) == len(tickers) and all(t.isupper() and t.isalpha() for t in tickers)


def test_search_options_include_etfs_and_ticker_normalization():
    options = search_options()
    assert options["NVDA"] == ("엔비디아", "반도체")
    assert options["QQQ"][1] == "ETF" and "QQQ" in options["QQQ"][0]
    assert normalize_ticker(" nvda ") == ["NVDA"]
    assert normalize_ticker("005930") == ["005930.KS", "005930.KQ"]
    assert normalize_ticker("  ") == []


def test_currency_formatting():
    assert currency_of("NVDA") == "USD" and currency_of("005930.KS") == "KRW" and currency_of("247540.KQ") == "KRW"
    assert fmt_money(5.46e12, "USD") == "5.46조 달러"
    assert fmt_money(3.9e11, "USD") == "3,900억 달러"
    assert fmt_money(12_345, "USD") == "$12,345" and fmt_money(-182.5, "USD") == "-$182.50"
    assert fmt_money(1.5e15, "KRW") == "1,500.0조 원"
    assert fmt_price(226.321, "USD") == "$226.32" and fmt_price(233000, "KRW") == "233,000원"


def test_parse_sec_filings_keeps_main_forms_and_counts_insiders():
    payload = {"filings": {"recent": {
        "form": ["4", "8-K", "4", "10-Q", "SC 13G", "10-K"],
        "filingDate": ["2026-10-09", "2026-09-30", "2026-09-01", "2026-08-27", "2026-08-01", "2026-02-20"],
        "accessionNumber": ["a", "0001045810-26-000101", "b", "0001045810-26-000090", "c", "0001045810-26-000010"],
        "primaryDocument": ["x.xml", "nvda-8k.htm", "y.xml", "nvda-10q.htm", "z.htm", "nvda-10k.htm"],
    }}}
    items, insider = sec.parse_filings(payload, 1045810, days=180, today=date(2026, 10, 13))
    assert [i["form"] for i in items] == ["8-K", "10-Q"]  # 10-K는 180일 밖, SC 13G는 목록에 없음
    assert items[0]["title"] == "주요 사항 보고"
    assert items[0]["url"] == "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000101/nvda-8k.htm"
    assert insider == 2


def test_recent_filings_uses_cached_ciks(tmp_path, monkeypatch):
    cache = tmp_path / "ciks.json"
    cache.write_text(json.dumps({"NVDA": 1045810}))
    monkeypatch.setattr(sec, "CIK_FILE", cache)
    urls = []

    def fake_get(url):
        urls.append(url)
        return json.dumps({"filings": {"recent": {}}}).encode()

    assert sec.recent_filings("nvda", get=fake_get) == ([], 0)
    assert urls == ["https://data.sec.gov/submissions/CIK0001045810.json"]
    with pytest.raises(sec.SecError):
        sec.recent_filings("ZZZZ", get=fake_get)


# DART
def test_parse_corp_codes_keeps_listed_companies_only():
    xml = ("<result><list><corp_code>00126380</corp_code><corp_name>삼성전자</corp_name><stock_code>005930</stock_code></list>"
           "<list><corp_code>00999999</corp_code><corp_name>비상장</corp_name><stock_code> </stock_code></list></result>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("CORPCODE.xml", xml)
    assert dart.parse_corp_codes(buf.getvalue()) == {"005930": "00126380"}


def test_parse_disclosures():
    payload = {"status": "000", "list": [{"rcept_dt": "20261012", "report_nm": "분기보고서 (2026.06) ",
                                          "flr_nm": "삼성전자", "rcept_no": "20261012000123"}]}
    [d] = dart.parse_disclosures(payload)
    assert d == {"date": "2026-10-12", "title": "분기보고서 (2026.06)", "filer": "삼성전자",
                 "url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20261012000123"}
    assert dart.parse_disclosures({"status": "013", "message": "조회된 데이타가 없습니다."}) == []
    with pytest.raises(dart.DartError):
        dart.parse_disclosures({"status": "020", "message": "요청 제한 초과"})


def test_recent_disclosures_uses_cached_corp_codes(tmp_path, monkeypatch):
    cache = tmp_path / "codes.json"
    cache.write_text(json.dumps({"005930": "00126380"}))
    monkeypatch.setattr(dart, "CORP_CODES_FILE", cache)
    calls = []

    def fake_get(path, params):
        calls.append((path, params))
        return json.dumps({"status": "013"}).encode()

    assert dart.recent_disclosures("005930.KS", "KEY", get=fake_get) == []
    assert calls[0][0] == "list.json" and calls[0][1]["corp_code"] == "00126380"
    with pytest.raises(dart.DartError):
        dart.recent_disclosures("999999.KS", "KEY", get=fake_get)


# AI 브리핑
SNAP = Snapshot(name="삼성전자", ticker="005930.KS", sector="반도체", market_cap=800e12,
                annuals=[A2025, A2024], metrics=compute([A2025, A2024], 800e12))
NEWS = [{"title": "3분기 영업이익 12조", "sentiment": "호재", "impact": 3},
        {"title": "분석 전 기사", "sentiment": None, "impact": None}]


class FakeClient:
    def __init__(self, text, stop_reason="end_turn"):
        self.calls = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))
        self.text, self.stop_reason = text, stop_reason

    def _create(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(stop_reason=self.stop_reason, content=[SimpleNamespace(type="text", text=self.text)])


def test_build_prompt_includes_metrics_average_and_analyzed_news_only():
    prompt = build_prompt(SNAP, {"per": 15.0}, NEWS)
    assert "PER: 20.0배 (업종 중간값 15.0배)" in prompt
    assert "2025 회계연도: 매출 300.0조 원" in prompt
    assert "[호재·영향 3] 3분기 영업이익 12조" in prompt and "분석 전 기사" not in prompt


def test_brief_parses_and_rejects():
    ok = json.dumps({"headline": "실적 회복", "strengths": ["a"], "weaknesses": ["b"], "checkpoints": ["c"]})
    result = brief(FakeClient(ok), SNAP, {}, NEWS)
    assert result.headline == "실적 회복"
    with pytest.raises(AnalysisError):
        brief(FakeClient(ok, stop_reason="refusal"), SNAP, {}, NEWS)
    with pytest.raises(AnalysisError):
        brief(FakeClient('{"headline": 1}'), SNAP, {}, NEWS)


def test_resolve_query_matches_names_tickers_and_codes():
    options = search_options()
    assert resolve_query("엔비디아", options) == ["NVDA"]  # 이름을 치고 바로 Enter
    assert resolve_query("nvda", options) == ["NVDA"]
    assert resolve_query("JP 모건", options) == ["JPM"]  # 띄어쓰기 무시
    assert resolve_query("팔란", options) == ["PLTR"]  # 한 곳만 포함하면 그 종목
    assert resolve_query("IONQ", options) == ["IONQ"]  # 목록에 없으면 티커로
    assert resolve_query("005930", options) == ["005930.KS", "005930.KQ"]
