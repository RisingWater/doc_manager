import sqlite3

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,
    file_name TEXT NOT NULL,
    ext TEXT,
    size INTEGER DEFAULT 0,
    mtime REAL DEFAULT 0,
    root_dir TEXT,
    rel_dir TEXT,
    year TEXT,
    subject TEXT,
    city TEXT,
    exam TEXT,
    paper_type TEXT NOT NULL DEFAULT '试卷',
    is_classified INTEGER NOT NULL DEFAULT 0,
    missing_dims TEXT NOT NULL DEFAULT '[]',
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_documents_year ON documents(year);
CREATE INDEX IF NOT EXISTS idx_documents_subject ON documents(subject);
CREATE INDEX IF NOT EXISTS idx_documents_city ON documents(city);
CREATE INDEX IF NOT EXISTS idx_documents_exam ON documents(exam);
CREATE INDEX IF NOT EXISTS idx_documents_classified ON documents(is_classified);
CREATE INDEX IF NOT EXISTS idx_documents_mtime ON documents(mtime);

CREATE TABLE IF NOT EXISTS scan_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trigger_type TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    files_found INTEGER DEFAULT 0,
    files_added INTEGER DEFAULT 0,
    files_skipped INTEGER DEFAULT 0,
    files_updated INTEGER DEFAULT 0,
    message TEXT
);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db() -> None:
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(documents)")]
        if "paper_type" not in cols:
            conn.execute("ALTER TABLE documents ADD COLUMN paper_type TEXT NOT NULL DEFAULT '试卷'")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_paper_type ON documents(paper_type)")
        conn.commit()
    finally:
        conn.close()
