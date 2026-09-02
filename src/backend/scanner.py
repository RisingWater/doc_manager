import json
import os
import threading
from datetime import datetime

from .classifier import DIM_KEYS, classify
from .config import SCAN_EXTENSIONS, load_doc_dirs
from .db import connect

INSERT_SQL = (
    "INSERT OR IGNORE INTO documents "
    "(path, file_name, ext, size, mtime, root_dir, rel_dir, "
    "year, subject, city, exam, paper_type, is_classified, missing_dims, first_seen_at, last_seen_at) "
    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
)

_scan_lock = threading.Lock()
_state_lock = threading.Lock()
_state = {"running": False, "scan_id": None}


def get_state() -> dict:
    with _state_lock:
        return dict(_state)


def _set_state(running: bool, scan_id: int | None) -> None:
    with _state_lock:
        _state["running"] = running
        _state["scan_id"] = scan_id


def start_scan(trigger: str = "manual") -> dict:
    if not _scan_lock.acquire(blocking=False):
        return {"ok": False, "message": "已有扫描任务在进行中，请稍后再试"}
    scan_id = None
    try:
        conn = connect()
        try:
            cur = conn.execute(
                "INSERT INTO scan_logs (trigger_type, status, started_at) VALUES (?, 'running', ?)",
                (trigger, datetime.now().isoformat(timespec="seconds")),
            )
            scan_id = cur.lastrowid
            conn.commit()
        finally:
            conn.close()
        _set_state(True, scan_id)
        threading.Thread(target=_scan_worker, args=(scan_id,), daemon=True).start()
        return {"ok": True, "scan_id": scan_id}
    except Exception as exc:
        _set_state(False, None)
        _scan_lock.release()
        if scan_id is not None:
            _finish_log(scan_id, "failed", 0, 0, 0, str(exc))
        return {"ok": False, "message": f"启动扫描失败：{exc}"}


def _scan_worker(scan_id: int) -> None:
    try:
        _run_scan(scan_id)
    finally:
        _set_state(False, None)
        _scan_lock.release()


def _run_scan(scan_id: int) -> None:
    conn = connect()
    files_found = files_added = files_skipped = files_updated = 0
    try:
        existing: dict[str, dict] = {}
        for r in conn.execute(
            "SELECT id, path, year, subject, city, exam, is_classified, missing_dims FROM documents"
        ):
            existing[r["path"]] = dict(r)
        roots = load_doc_dirs()
        now = datetime.now().isoformat(timespec="seconds")
        batch: list[tuple] = []
        for root in roots:
            if not os.path.isdir(root):
                continue
            root = os.path.normpath(root)
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if not d.startswith(".")]
                for name in filenames:
                    if _skip_file(name):
                        continue
                    if os.path.splitext(name)[1].lower() not in SCAN_EXTENSIONS:
                        continue
                    files_found += 1
                    full = os.path.normpath(os.path.join(dirpath, name))
                    if full in existing:
                        files_skipped += 1
                        files_updated += _reclassify(conn, existing[full], root, dirpath, name)
                        continue
                    existing[full] = {}
                    batch.append(_build_row(root, dirpath, name, full, now))
                    if len(batch) >= 500:
                        files_added += _flush(conn, batch)
        files_added += _flush(conn, batch)
        _finish_log(scan_id, "finished", files_found, files_added, files_skipped, None, files_updated)
    except Exception as exc:
        _finish_log(scan_id, "failed", files_found, files_added, files_skipped, str(exc), files_updated)
    finally:
        conn.close()


def _reclassify(conn, row: dict, root: str, dirpath: str, name: str) -> int:
    dims, missing = _classify_parts(root, dirpath, name)
    new_missing = json.dumps(missing, ensure_ascii=False)
    current = (
        row["year"], row["subject"], row["city"], row["exam"],
        row["paper_type"] if "paper_type" in row.keys() else None, row["missing_dims"],
    )
    updated = (
        dims["year"], dims["subject"], dims["city"], dims["exam"],
        dims["paper_type"], new_missing,
    )
    if current == updated:
        return 0
    conn.execute(
        "UPDATE documents SET year=?, subject=?, city=?, exam=?, paper_type=?, is_classified=?, missing_dims=? WHERE id=?",
        (dims["year"], dims["subject"], dims["city"], dims["exam"], dims["paper_type"], 0 if missing else 1, new_missing, row["id"]),
    )
    conn.commit()
    return 1


def _classify_parts(root: str, dirpath: str, name: str) -> tuple[dict[str, str | None], list[str]]:
    rel = os.path.relpath(dirpath, root)
    dir_segments = [] if rel == "." else rel.split(os.sep)
    stem = os.path.splitext(name)[0]
    return classify(dir_segments, stem)


def insert_document(
    path: str,
    root: str,
    year: str | None = None,
    subject: str | None = None,
    city: str | None = None,
    exam: str | None = None,
    paper_type: str | None = None,
) -> int:
    conn = connect()
    try:
        now = datetime.now().isoformat(timespec="seconds")
        st = os.stat(path)
        name = os.path.basename(path)
        rel = os.path.relpath(os.path.dirname(path), root)
        dims = {
            "year": (year or "").strip() or None,
            "subject": (subject or "").strip() or None,
            "city": (city or "").strip() or None,
            "exam": (exam or "").strip() or None,
            "paper_type": (paper_type or "").strip() or "试卷",
        }
        missing = [k for k in DIM_KEYS if not dims[k]]
        cur = conn.execute(
            INSERT_SQL,
            (
                path, name, os.path.splitext(name)[1].lower().lstrip("."), st.st_size, st.st_mtime,
                root, "" if rel == "." else rel,
                dims["year"], dims["subject"], dims["city"], dims["exam"], dims["paper_type"],
                0 if missing else 1, json.dumps(missing, ensure_ascii=False), now, now,
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _build_row(root: str, dirpath: str, name: str, full: str, now: str) -> tuple:
    rel = os.path.relpath(dirpath, root)
    dims, missing = _classify_parts(root, dirpath, name)
    st = os.stat(os.path.join(dirpath, name))
    return (
        full, name, os.path.splitext(name)[1].lower().lstrip("."), st.st_size, st.st_mtime,
        root, "" if rel == "." else rel,
        dims["year"], dims["subject"], dims["city"], dims["exam"], dims["paper_type"],
        0 if missing else 1, json.dumps(missing, ensure_ascii=False), now, now,
    )


def _flush(conn, batch: list[tuple]) -> int:
    if not batch:
        return 0
    before = conn.total_changes
    conn.executemany(INSERT_SQL, batch)
    conn.commit()
    added = conn.total_changes - before
    batch.clear()
    return added


def _skip_file(name: str) -> bool:
    return name.startswith(".") or name.startswith("~$") or name in {"Thumbs.db", "desktop.ini"}


def _finish_log(scan_id: int, status: str, found: int, added: int, skipped: int, message: str | None, updated: int = 0) -> None:
    conn = connect()
    try:
        conn.execute(
            "UPDATE scan_logs SET status=?, finished_at=?, files_found=?, files_added=?, files_skipped=?, files_updated=?, message=? WHERE id=?",
            (status, datetime.now().isoformat(timespec="seconds"), found, added, skipped, updated, message, scan_id),
        )
        conn.commit()
    finally:
        conn.close()
