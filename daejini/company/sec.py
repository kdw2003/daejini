"""미국 SEC EDGAR 공시 (무료, API 키 불필요).

SEC는 연락처가 들어간 User-Agent를 요구한다. .env의 SEC_USER_AGENT에
"앱이름 본인이메일" 형식으로 넣어 두면 그 값을 쓴다.
"""
import json
import os
import urllib.request
from datetime import date, timedelta
from pathlib import Path

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"
CIK_FILE = Path(__file__).resolve().parents[2] / "data" / "sec_ciks.json"
DEFAULT_USER_AGENT = "daejini personal-research-app admin@daejini.local"

# 보여줄 주요 공시와 쉬운 이름. 내부자 거래(Form 4)는 건수만 센다.
FORMS = {
    "10-K": "연간 보고서",
    "10-Q": "분기 보고서",
    "8-K": "주요 사항 보고",
    "20-F": "연간 보고서 (해외 기업)",
    "6-K": "수시 보고 (해외 기업)",
    "DEF 14A": "주주총회 안건",
    "S-1": "증권 신고서",
}
INSIDER_FORM = "4"


class SecError(Exception):
    pass


def _get(url: str) -> bytes:
    ua = os.environ.get("SEC_USER_AGENT") or DEFAULT_USER_AGENT
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept-Encoding": "identity"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read()


def ciks(get=_get) -> dict[str, int]:
    """{티커: CIK}. 한 번 받아 data/에 저장해 두고 재사용한다."""
    if CIK_FILE.exists():
        return json.loads(CIK_FILE.read_text(encoding="utf-8"))
    raw = json.loads(get(TICKERS_URL))
    table = {row["ticker"].upper(): int(row["cik_str"]) for row in raw.values()}
    CIK_FILE.write_text(json.dumps(table), encoding="utf-8")
    return table


def parse_filings(payload: dict, cik: int, days: int = 180, limit: int = 12, today: date | None = None):
    """(주요 공시 목록, 기간 내 내부자 거래 건수)"""
    recent = payload.get("filings", {}).get("recent", {})
    since = ((today or date.today()) - timedelta(days=days)).isoformat()
    items, insider = [], 0
    for form, filed, acc, doc in zip(recent.get("form", []), recent.get("filingDate", []),
                                     recent.get("accessionNumber", []), recent.get("primaryDocument", [])):
        if filed < since:
            break  # 최신순으로 정렬돼 있음
        if form == INSIDER_FORM:
            insider += 1
        elif form in FORMS and len(items) < limit:
            items.append({
                "date": filed,
                "form": form,
                "title": FORMS[form],
                "url": ARCHIVE_URL.format(cik=cik, acc=acc.replace("-", ""), doc=doc),
            })
    return items, insider


def recent_filings(ticker: str, days: int = 180, get=_get):
    cik = ciks(get).get(ticker.upper())
    if cik is None:
        raise SecError(f"{ticker}의 SEC 등록 번호(CIK)를 찾지 못했어요.")
    return parse_filings(json.loads(get(SUBMISSIONS_URL.format(cik=cik))), cik, days=days)
