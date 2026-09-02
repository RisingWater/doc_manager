import json
import os
from datetime import datetime

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from . import scanner
from .config import UPLOAD_DIR, load_doc_dirs
from .db import connect

router = APIRouter(prefix="/api")

SORT_OPTIONS = {
    "mtime_desc": "mtime DESC, id DESC",
    "mtime_asc": "mtime ASC, id ASC",
    "name_asc": "file_name COLLATE NOCASE ASC, id ASC",
    "name_desc": "file_name COLLATE NOCASE DESC, id DESC",
}

LIKE_COLUMNS = ["file_name", "path", "year", "subject", "city", "exam", "paper_type"]


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _split_values(raw: str) -> list[str]:
    return [v.strip() for v in raw.split(",") if v.strip()]


@router.get("/meta/options")
def meta_options():
    conn = connect()
    try:

        def options_for(col: str, order: str = "ASC") -> list[dict]:
            rows = conn.execute(
                f"SELECT {col} AS value, COUNT(*) AS count FROM documents "
                f"WHERE {col} IS NOT NULL AND {col} != '' GROUP BY {col} ORDER BY {col} {order}"
            ).fetchall()
            return [dict(r) for r in rows]

        totals = conn.execute(
            "SELECT COUNT(*) AS total, COALESCE(SUM(is_classified), 0) AS classified FROM documents"
        ).fetchone()
        return {
            "years": options_for("year", "DESC"),
            "subjects": options_for("subject"),
            "cities": options_for("city"),
            "exams": options_for("exam"),
            "paper_types": options_for("paper_type"),
            "total": totals["total"],
            "classified": totals["classified"],
        }
    finally:
        conn.close()


@router.get("/documents")
def list_documents(
    years: str = "",
    subjects: str = "",
    cities: str = "",
    exams: str = "",
    classified: str = "",
    paper_type: str = "",
    q: str = "",
    sort: str = "mtime_desc",
    page: int = 1,
    page_size: int = 20,
):
    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    clauses: list[str] = []
    params: list = []

    def add_in(raw: str, col: str) -> None:
        values = _split_values(raw)
        if values:
            clauses.append(f"{col} IN ({', '.join('?' * len(values))})")
            params.extend(values)

    add_in(years, "year")
    add_in(subjects, "subject")
    add_in(cities, "city")
    add_in(exams, "exam")
    add_in(paper_type, "paper_type")
    if classified == "yes":
        clauses.append("is_classified = 1")
    elif classified == "no":
        clauses.append("is_classified = 0")
    keyword = q.strip()
    if keyword:
        like = f"%{_escape_like(keyword)}%"
        parts = [f"{col} LIKE ? ESCAPE '\\'" for col in LIKE_COLUMNS]
        clauses.append("(" + " OR ".join(parts) + ")")
        params.extend([like] * len(LIKE_COLUMNS))

    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    order = SORT_OPTIONS.get(sort, SORT_OPTIONS["mtime_desc"])

    conn = connect()
    try:
        total = conn.execute(f"SELECT COUNT(*) FROM documents{where}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT id, path, file_name, ext, size, mtime, rel_dir, "
            f"year, subject, city, exam, paper_type, is_classified, missing_dims "
            f"FROM documents{where} ORDER BY {order} LIMIT ? OFFSET ?",
            [*params, page_size, (page - 1) * page_size],
        ).fetchall()
    finally:
        conn.close()

    items = []
    for r in rows:
        item = dict(r)
        item["is_classified"] = bool(item["is_classified"])
        item["missing_dims"] = json.loads(item["missing_dims"])
        item["mtime"] = (
            datetime.fromtimestamp(item["mtime"]).isoformat(timespec="seconds") if item["mtime"] else None
        )
        items.append(item)
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.get("/documents/{doc_id}/download")
def download_document(doc_id: int):
    conn = connect()
    try:
        row = conn.execute("SELECT path, file_name FROM documents WHERE id = ?", (doc_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    if not os.path.isfile(row["path"]):
        raise HTTPException(status_code=404, detail="文件在磁盘上不存在")
    return FileResponse(row["path"], filename=row["file_name"])


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    year: str = Form(""),
    subject: str = Form(""),
    city: str = Form(""),
    exam: str = Form(""),
    root_dir: str = Form(""),
):
    name = os.path.basename(file.filename or "").strip()
    if not name or name in {".", ".."}:
        raise HTTPException(status_code=400, detail="文件名无效")
    name = name.replace("\\", "_").replace("/", "_")

    values = {"year": year.strip(), "subject": subject.strip(), "city": city.strip(), "exam": exam.strip()}
    for key, value in values.items():
        if value in {".", ".."} or "/" in value or "\\" in value:
            raise HTTPException(status_code=400, detail=f"分类值不合法：{key}={value}")

    configured = load_doc_dirs()
    target_root = os.path.normpath(root_dir.strip()) if root_dir.strip() else str(UPLOAD_DIR)
    if root_dir.strip() and target_root not in [os.path.normpath(d) for d in configured]:
        raise HTTPException(status_code=400, detail="目标目录不在 docs.json 配置中")

    target_sub = os.path.join(target_root, *[v for v in values.values() if v])
    os.makedirs(target_sub, exist_ok=True)
    dest = os.path.join(target_sub, name)
    base, ext = os.path.splitext(dest)
    i = 1
    while os.path.exists(dest):
        dest = f"{base}({i}){ext}"
        i += 1

    try:
        with open(dest, "wb") as f:
            while chunk := await file.read(1024 * 1024):
                f.write(chunk)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"保存文件失败：{exc}")

    doc_id = scanner.insert_document(dest, os.path.normpath(target_root), **values)
    return {"ok": True, "id": doc_id, "path": dest, "file_name": os.path.basename(dest)}


@router.post("/scan")
def trigger_scan():
    result = scanner.start_scan("manual")
    if not result.get("ok"):
        raise HTTPException(status_code=409, detail=result.get("message", "无法启动扫描"))
    return result


@router.get("/scan/status")
def scan_status():
    state = scanner.get_state()
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM scan_logs ORDER BY id DESC LIMIT 1").fetchone()
    finally:
        conn.close()
    return {
        "running": state["running"],
        "scan_id": state["scan_id"],
        "last": _log_to_dict(row) if row else None,
    }


@router.get("/scan/logs")
def scan_logs(limit: int = 20):
    limit = min(max(1, limit), 100)
    conn = connect()
    try:
        rows = conn.execute("SELECT * FROM scan_logs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    finally:
        conn.close()
    return [_log_to_dict(r) for r in rows]


@router.get("/dirs")
def get_dirs():
    return [{"path": p, "exists": os.path.isdir(p)} for p in load_doc_dirs()]


def _log_to_dict(row) -> dict:
    return dict(row)
