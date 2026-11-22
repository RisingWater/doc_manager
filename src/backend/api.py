import json
import os
from datetime import datetime

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import scanner
from .config import UPLOAD_DIR, load_doc_dirs
from .db import connect

router = APIRouter(prefix="/api")

SORT_OPTIONS = {
    "mtime_desc": "mtime DESC, id DESC",
    "mtime_asc": "mtime ASC, id ASC",
    "name_asc": "file_name COLLATE NOCASE ASC, id ASC",
    "name_desc": "file_name COLLATE NOCASE DESC, id DESC",
    "score_desc": "score IS NULL ASC, score DESC, id DESC",
    "score_asc": "score IS NULL ASC, score ASC, id ASC",
}

SCORE_OPS = {"gt": ">", "gte": ">=", "eq": "=", "lte": "<=", "lt": "<"}
MAX_SCORE = 1000.0

LIKE_COLUMNS = ["file_name", "path", "year", "subject", "city", "exam", "paper_type"]


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _split_values(raw: str) -> list[str]:
    return [v.strip() for v in raw.split(",") if v.strip()]


class ProgressUpdate(BaseModel):
    done: bool | None = None
    score: float | None = None


class MarkPayload(BaseModel):
    ids: list[int]
    done: bool = True


def _validate_score(value: float | None) -> float | None:
    if value is None:
        return None
    if value < 0 or value > MAX_SCORE:
        raise HTTPException(status_code=400, detail=f"分数需在 0 ~ {int(MAX_SCORE)} 之间")
    return round(float(value), 1)


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
            "SELECT COUNT(*) AS total, COALESCE(SUM(is_classified), 0) AS classified, "
            "COALESCE(SUM(done), 0) AS done, COUNT(score) AS scored, AVG(score) AS avg_score "
            "FROM documents"
        ).fetchone()
        avg_score = totals["avg_score"]
        return {
            "years": options_for("year", "DESC"),
            "subjects": options_for("subject"),
            "cities": options_for("city"),
            "exams": options_for("exam"),
            "paper_types": options_for("paper_type"),
            "total": totals["total"],
            "classified": totals["classified"],
            "done": totals["done"],
            "scored": totals["scored"],
            "avg_score": round(avg_score, 1) if avg_score is not None else None,
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
    done: str = "",
    score_op: str = "",
    score_value: str = "",
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
    paper_values = _split_values(paper_type)
    if paper_values:
        if "试卷" in paper_values or "答案" in paper_values:
            paper_values = list(dict.fromkeys([*paper_values, "试卷+答案"]))
        clauses.append(f"paper_type IN ({', '.join('?' * len(paper_values))})")
        params.extend(paper_values)
    if classified == "yes":
        clauses.append("is_classified = 1")
    elif classified == "no":
        clauses.append("is_classified = 0")
    if done == "yes":
        clauses.append("done = 1")
    elif done == "no":
        clauses.append("done = 0")
    op = SCORE_OPS.get(score_op)
    if op and score_value.strip():
        try:
            score_limit = float(score_value.strip())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"分数不合法：{score_value}")
        # 没有分数的卷子不参与比较，始终保留
        clauses.append(f"(score IS NULL OR score {op} ?)")
        params.append(score_limit)
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
            f"year, subject, city, exam, paper_type, is_classified, missing_dims, "
            f"done, done_at, score "
            f"FROM documents{where} ORDER BY {order} LIMIT ? OFFSET ?",
            [*params, page_size, (page - 1) * page_size],
        ).fetchall()
    finally:
        conn.close()

    items = []
    for r in rows:
        item = dict(r)
        item["is_classified"] = bool(item["is_classified"])
        item["done"] = bool(item["done"])
        item["missing_dims"] = json.loads(item["missing_dims"])
        item["mtime"] = (
            datetime.fromtimestamp(item["mtime"]).isoformat(timespec="seconds") if item["mtime"] else None
        )
        items.append(item)
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.patch("/documents/{doc_id}")
def update_progress(doc_id: int, payload: ProgressUpdate):
    fields = payload.model_fields_set
    if not fields:
        raise HTTPException(status_code=400, detail="没有需要更新的字段")
    conn = connect()
    try:
        row = conn.execute(
            "SELECT id, done, done_at, score FROM documents WHERE id = ?", (doc_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="文档不存在")
        is_done = bool(row["done"])
        done_at = row["done_at"]
        score = row["score"]
        if "done" in fields and payload.done is not None:
            is_done = payload.done
        if "score" in fields:
            score = _validate_score(payload.score)
            if score is not None:
                is_done = True
        if not is_done:
            score = None
            done_at = None
        elif done_at is None:
            done_at = datetime.now().isoformat(timespec="seconds")
        conn.execute(
            "UPDATE documents SET done = ?, done_at = ?, score = ? WHERE id = ?",
            (1 if is_done else 0, done_at, score, doc_id),
        )
        conn.commit()
    finally:
        conn.close()
    return {"id": doc_id, "done": is_done, "done_at": done_at, "score": score}


@router.post("/documents/mark")
def mark_documents(payload: MarkPayload):
    ids = list(dict.fromkeys(int(i) for i in payload.ids))[:1000]
    if not ids:
        raise HTTPException(status_code=400, detail="没有选择文档")
    placeholders = ", ".join("?" * len(ids))
    conn = connect()
    try:
        if payload.done:
            cur = conn.execute(
                f"UPDATE documents SET done = 1, done_at = COALESCE(done_at, ?) "
                f"WHERE id IN ({placeholders})",
                [datetime.now().isoformat(timespec="seconds"), *ids],
            )
        else:
            cur = conn.execute(
                f"UPDATE documents SET done = 0, done_at = NULL, score = NULL "
                f"WHERE id IN ({placeholders})",
                ids,
            )
        conn.commit()
        updated = cur.rowcount
    finally:
        conn.close()
    return {"ok": True, "updated": updated}


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
