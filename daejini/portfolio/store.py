"""보유 종목 저장 (뉴스와 같은 SQLite 파일, 별도 테이블)."""
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..news.store import DEFAULT_DB

SCHEMA = """
CREATE TABLE IF NOT EXISTS holdings (
    ticker TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    sector TEXT NOT NULL,
    quantity REAL NOT NULL CHECK (quantity > 0),
    avg_price REAL NOT NULL CHECK (avg_price > 0),
    added_at TEXT NOT NULL
);
"""


@dataclass
class Holding:
    ticker: str
    name: str
    sector: str
    quantity: float
    avg_price: float

    @property
    def cost(self) -> float:
        return self.quantity * self.avg_price


class PortfolioStore:
    def __init__(self, path=DEFAULT_DB):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def holdings(self) -> list[Holding]:
        rows = self.conn.execute(
            "SELECT ticker, name, sector, quantity, avg_price FROM holdings ORDER BY added_at"
        )
        return [Holding(**dict(r)) for r in rows]

    def buy(self, ticker: str, name: str, sector: str, quantity: float, price: float) -> Holding:
        """보유 중이면 추가 매수로 보고 평균단가를 다시 계산한다."""
        if quantity <= 0 or price <= 0:
            raise ValueError("수량과 단가는 0보다 커야 해요.")
        row = self.conn.execute("SELECT quantity, avg_price FROM holdings WHERE ticker = ?", (ticker,)).fetchone()
        with self.conn:
            if row:
                total_qty = row["quantity"] + quantity
                avg = (row["quantity"] * row["avg_price"] + quantity * price) / total_qty
                self.conn.execute(
                    "UPDATE holdings SET quantity = ?, avg_price = ? WHERE ticker = ?", (total_qty, avg, ticker)
                )
            else:
                self.conn.execute(
                    "INSERT INTO holdings VALUES (?, ?, ?, ?, ?, ?)",
                    (ticker, name, sector, quantity, price, datetime.now(timezone.utc).isoformat()),
                )
        return next(h for h in self.holdings() if h.ticker == ticker)

    def update(self, ticker: str, quantity: float, avg_price: float) -> None:
        if quantity <= 0 or avg_price <= 0:
            raise ValueError("수량과 단가는 0보다 커야 해요.")
        with self.conn:
            self.conn.execute(
                "UPDATE holdings SET quantity = ?, avg_price = ? WHERE ticker = ?", (quantity, avg_price, ticker)
            )

    def export(self) -> dict:
        """백업용: 보유 종목 전체를 JSON으로 저장할 수 있는 dict로."""
        return {"version": 1, "holdings": [
            {"ticker": h.ticker, "name": h.name, "sector": h.sector, "quantity": h.quantity, "avg_price": h.avg_price}
            for h in self.holdings()
        ]}

    def restore(self, backup: dict) -> int:
        """백업을 불러와 현재 보유 종목을 통째로 바꾼다. 형식이 틀리면 아무것도 바꾸지 않는다."""
        rows = backup.get("holdings") if isinstance(backup, dict) else None
        if not isinstance(rows, list):
            raise ValueError("대지니 포트폴리오 백업 파일이 아니에요.")
        clean = []
        for r in rows:
            try:
                h = Holding(str(r["ticker"]).strip().upper(), str(r["name"]).strip(), str(r.get("sector") or "기타"),
                            float(r["quantity"]), float(r["avg_price"]))
            except (KeyError, TypeError, ValueError):
                raise ValueError("백업 파일의 종목 정보가 올바르지 않아요.") from None
            if not h.ticker or h.quantity <= 0 or h.avg_price <= 0:
                raise ValueError(f"{h.ticker or '이름 없는 종목'}의 수량이나 단가가 올바르지 않아요.")
            clean.append(h)
        now = datetime.now(timezone.utc).isoformat()
        with self.conn:
            self.conn.execute("DELETE FROM holdings")
            for h in clean:
                self.conn.execute(
                    "INSERT OR REPLACE INTO holdings VALUES (?, ?, ?, ?, ?, ?)",
                    (h.ticker, h.name, h.sector, h.quantity, h.avg_price, now),
                )
        return len(clean)

    def remove(self, ticker: str) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM holdings WHERE ticker = ?", (ticker,))
