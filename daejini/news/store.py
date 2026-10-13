"""관심 키워드, 기사, 분석 결과 저장 (SQLite)."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "news.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS keywords (
    keyword TEXT PRIMARY KEY,
    added_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY,
    url TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    source TEXT,
    published TEXT,
    fetched_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS article_keywords (
    article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    keyword TEXT NOT NULL,
    PRIMARY KEY (article_id, keyword)
);
CREATE TABLE IF NOT EXISTS verdicts (
    article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    keyword TEXT NOT NULL,
    sentiment TEXT NOT NULL,
    impact INTEGER NOT NULL,
    target TEXT,
    reason TEXT,
    model TEXT,
    analyzed_at TEXT NOT NULL,
    PRIMARY KEY (article_id, keyword)
);
CREATE TABLE IF NOT EXISTS summaries (
    keyword TEXT PRIMARY KEY,
    lines TEXT NOT NULL,
    article_ids TEXT NOT NULL,
    model TEXT,
    created_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path=DEFAULT_DB):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)

    # 관심 키워드
    def keywords(self) -> list[str]:
        rows = self.conn.execute("SELECT keyword FROM keywords ORDER BY added_at")
        return [r["keyword"] for r in rows]

    def add_keyword(self, keyword: str) -> bool:
        keyword = keyword.strip()
        if not keyword:
            return False
        with self.conn:
            cur = self.conn.execute(
                "INSERT OR IGNORE INTO keywords VALUES (?, ?)", (keyword, _now())
            )
        return cur.rowcount == 1

    def remove_keyword(self, keyword: str) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM keywords WHERE keyword = ?", (keyword,))
            self.conn.execute("DELETE FROM article_keywords WHERE keyword = ?", (keyword,))
            self.conn.execute("DELETE FROM verdicts WHERE keyword = ?", (keyword,))
            self.conn.execute("DELETE FROM summaries WHERE keyword = ?", (keyword,))

    # 기사
    def save_articles(self, keyword: str, articles) -> int:
        """기사를 저장하고 이 키워드에 새로 붙은 기사 수를 돌려준다."""
        added = 0
        with self.conn:
            for a in articles:
                self.conn.execute(
                    "INSERT OR IGNORE INTO articles (url, title, source, published, fetched_at)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (a.url, a.title, a.source, a.published, _now()),
                )
                article_id = self.conn.execute(
                    "SELECT id FROM articles WHERE url = ?", (a.url,)
                ).fetchone()["id"]
                cur = self.conn.execute(
                    "INSERT OR IGNORE INTO article_keywords VALUES (?, ?)", (article_id, keyword)
                )
                added += cur.rowcount
        return added

    def recent_articles(self, keyword: str, since: str, limit: int = 30) -> list[dict]:
        """최근 기사와 (있으면) 분석 결과. 최신순."""
        rows = self.conn.execute(
            """
            SELECT a.id, a.url, a.title, a.source, a.published,
                   v.sentiment, v.impact, v.target, v.reason
            FROM articles a
            JOIN article_keywords k ON k.article_id = a.id AND k.keyword = ?
            LEFT JOIN verdicts v ON v.article_id = a.id AND v.keyword = k.keyword
            WHERE a.published >= ?
            ORDER BY a.published DESC
            LIMIT ?
            """,
            (keyword, since, limit),
        )
        return [dict(r) for r in rows]

    # 분석 결과
    def save_report(self, keyword: str, report, article_ids: list[int], model: str) -> None:
        now = _now()
        with self.conn:
            for v in report.verdicts:
                self.conn.execute(
                    "INSERT OR REPLACE INTO verdicts VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (v.id, keyword, v.sentiment, v.impact, v.target, v.reason, model, now),
                )
            self.conn.execute(
                "INSERT OR REPLACE INTO summaries VALUES (?, ?, ?, ?, ?)",
                (keyword, json.dumps(report.summary, ensure_ascii=False),
                 json.dumps(sorted(article_ids)), model, now),
            )

    def summary(self, keyword: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM summaries WHERE keyword = ?", (keyword,)).fetchone()
        if row is None:
            return None
        return {
            "lines": json.loads(row["lines"]),
            "article_ids": json.loads(row["article_ids"]),
            "model": row["model"],
            "created_at": row["created_at"],
        }
