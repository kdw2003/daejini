"""DART 오픈API: 최근 공시 목록. 키 발급: https://opendart.fss.or.kr (무료)"""
import io
import json
import os
import urllib.parse
import urllib.request
import zipfile
from datetime import date, timedelta
from pathlib import Path
from xml.etree import ElementTree

BASE = "https://opendart.fss.or.kr/api"
CORP_CODES_FILE = Path(__file__).resolve().parents[2] / "data" / "dart_corp_codes.json"
VIEWER = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo={}"


class DartError(Exception):
    pass


def api_key() -> str | None:
    return os.environ.get("DART_API_KEY") or None


def _get(path: str, params: dict) -> bytes:
    url = f"{BASE}/{path}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=20) as resp:
        return resp.read()


def parse_corp_codes(zip_bytes: bytes) -> dict[str, str]:
    """corpCode.xml(zip) → {종목코드 6자리: 고유번호 8자리}. 상장사만."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        xml = zf.read(zf.namelist()[0])
    root = ElementTree.fromstring(xml)
    codes = {}
    for item in root.iter("list"):
        stock = (item.findtext("stock_code") or "").strip()
        if stock:
            codes[stock] = item.findtext("corp_code").strip()
    return codes


def corp_codes(key: str, get=_get) -> dict[str, str]:
    """고유번호 표는 한 번 받아서 data/에 저장해 두고 재사용한다."""
    if CORP_CODES_FILE.exists():
        return json.loads(CORP_CODES_FILE.read_text(encoding="utf-8"))
    raw = get("corpCode.xml", {"crtfc_key": key})
    if not raw.startswith(b"PK"):  # zip이 아니면 오류 응답(JSON/XML)
        raise DartError(f"고유번호 목록을 받지 못했어요: {raw[:200].decode('utf-8', 'replace')}")
    codes = parse_corp_codes(raw)
    CORP_CODES_FILE.write_text(json.dumps(codes), encoding="utf-8")
    return codes


def parse_disclosures(payload: dict) -> list[dict]:
    status = payload.get("status")
    if status == "013":  # 조회된 데이터 없음
        return []
    if status != "000":
        raise DartError(f"DART 오류 {status}: {payload.get('message', '')}")
    return [
        {
            "date": f"{d['rcept_dt'][:4]}-{d['rcept_dt'][4:6]}-{d['rcept_dt'][6:]}",
            "title": d["report_nm"].strip(),
            "filer": d.get("flr_nm", ""),
            "url": VIEWER.format(d["rcept_no"]),
        }
        for d in payload.get("list", [])
    ]


def recent_disclosures(ticker: str, key: str, days: int = 90, limit: int = 15, get=_get) -> list[dict]:
    stock_code = ticker.split(".")[0]
    corp_code = corp_codes(key, get).get(stock_code)
    if corp_code is None:
        raise DartError(f"{stock_code}의 DART 고유번호를 찾지 못했어요.")
    today = date.today()
    raw = get("list.json", {
        "crtfc_key": key,
        "corp_code": corp_code,
        "bgn_de": (today - timedelta(days=days)).strftime("%Y%m%d"),
        "end_de": today.strftime("%Y%m%d"),
        "page_count": limit,
    })
    return parse_disclosures(json.loads(raw))
