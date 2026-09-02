import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "doc_manager.db"
DOCS_JSON_PATH = BASE_DIR / "docs.json"
UPLOAD_DIR = BASE_DIR / "uploads"
FRONTEND_DIST_DIR = BASE_DIR / "src" / "frontend" / "dist"

DATA_DIR.mkdir(parents=True, exist_ok=True)

SCAN_INTERVAL_MINUTES = int(os.environ.get("SCAN_INTERVAL_MINUTES", "30"))

SCAN_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".zip", ".rar", ".7z",
    ".mp4",
}

SUBJECTS = [
    "语文", "数学", "英语", "物理", "化学", "生物",
    "道德与法治", "德与法治", "道法", "政治", "历史", "地理",
    "科学", "体育与健康", "体育",
]
SUBJECTS.sort(key=len, reverse=True)

CITIES = [
    "福州市", "厦门市", "莆田市", "三明市", "泉州市",
    "漳州市", "南平市", "龙岩市", "宁德市",
]


def load_doc_dirs() -> list[str]:
    if not DOCS_JSON_PATH.exists():
        return []
    try:
        raw = json.loads(DOCS_JSON_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        items = raw.get("directories", [])
    else:
        items = []
    dirs: list[str] = []
    for item in items:
        p = Path(str(item).strip())
        if not p.is_absolute():
            p = BASE_DIR / p
        dirs.append(str(p))
    return dirs
