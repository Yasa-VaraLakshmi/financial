import asyncio
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from crewai import Crew, Process
from agents import create_agents
from task import build_tasks
from tools import build_document_excerpt

DEFAULT_QUERY = "Analyze this financial document for investment insights."
DATA_DIR = "data"
DB_PATH = "analysis.db"
ALLOWED_CONTENT_TYPES = {"application/pdf"}

app = FastAPI(title="Financial Document Analyzer")

job_queue: asyncio.Queue[str] = asyncio.Queue()
job_events: dict[str, asyncio.Event] = {}
queue_worker_task: asyncio.Task | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _init_db() -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS analyses (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                status TEXT NOT NULL,
                query TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                file_path TEXT NOT NULL,
                result TEXT,
                error TEXT
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def _insert_job(job_id: str, query: str, original_filename: str, file_path: str) -> None:
    now = _utc_now()
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            """
            INSERT INTO analyses (id, created_at, updated_at, status, query, original_filename, file_path)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (job_id, now, now, "queued", query, original_filename, file_path),
        )
        conn.commit()
    finally:
        conn.close()


def _update_job(job_id: str, status: str, result: str | None = None, error: str | None = None) -> None:
    now = _utc_now()
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            """
            UPDATE analyses
            SET updated_at = ?, status = ?, result = ?, error = ?
            WHERE id = ?
            """,
            (now, status, result, error, job_id),
        )
        conn.commit()
    finally:
        conn.close()


def _fetch_job(job_id: str) -> Dict[str, Any] | None:
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM analyses WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            return None
        return dict(row)
    finally:
        conn.close()


def run_crew(query: str, file_path: str) -> str:
    agents = create_agents()
    tasks = build_tasks(agents)
    document_excerpt = build_document_excerpt(file_path)

    financial_crew = Crew(
        agents=[agents["verifier"], agents["analyst"]],
        tasks=tasks,
        process=Process.sequential,
        verbose=False,
    )
    result = financial_crew.kickoff(inputs={"query": query, "document_excerpt": document_excerpt})
    return str(result)


async def _process_job(job_id: str) -> None:
    record = _fetch_job(job_id)
    if record is None:
        return

    _update_job(job_id, status="processing")
    try:
        result = await asyncio.to_thread(run_crew, record["query"], record["file_path"])
        _update_job(job_id, status="completed", result=result, error=None)
    except Exception as exc:
        _update_job(job_id, status="failed", result=None, error=str(exc))
    finally:
        file_path = record["file_path"]
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass

        event = job_events.get(job_id)
        if event is not None:
            event.set()
        job_events.pop(job_id, None)


async def _worker_loop() -> None:
    while True:
        job_id = await job_queue.get()
        try:
            await _process_job(job_id)
        finally:
            job_queue.task_done()


@app.on_event("startup")
async def startup() -> None:
    global queue_worker_task
    os.makedirs(DATA_DIR, exist_ok=True)
    _init_db()
    if queue_worker_task is None or queue_worker_task.done():
        queue_worker_task = asyncio.create_task(_worker_loop())


@app.on_event("shutdown")
async def shutdown() -> None:
    global queue_worker_task
    if queue_worker_task is not None:
        queue_worker_task.cancel()
        try:
            await queue_worker_task
        except asyncio.CancelledError:
            pass


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Financial Document Analyzer API is running"}


@app.post("/analyze")
async def analyze_financial_document(
    file: UploadFile = File(...),
    query: str = Form(default=DEFAULT_QUERY),
    wait: bool = Form(default=True),
) -> Dict[str, Any]:
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    cleaned_query = (query or DEFAULT_QUERY).strip() or DEFAULT_QUERY
    job_id = str(uuid.uuid4())
    file_path = os.path.join(DATA_DIR, f"financial_document_{job_id}.pdf")

    try:
        with open(file_path, "wb") as f:
            f.write(await file.read())

        _insert_job(job_id, cleaned_query, file.filename or "uploaded.pdf", file_path)
        event = asyncio.Event()
        job_events[job_id] = event
        await job_queue.put(job_id)

        if not wait:
            return {
                "status": "queued",
                "job_id": job_id,
                "query": cleaned_query,
            }

        await event.wait()
        record = _fetch_job(job_id)
        if record is None:
            raise HTTPException(status_code=500, detail="Job completed but record was not found.")
        if record["status"] == "failed":
            raise HTTPException(status_code=500, detail=record["error"] or "Unknown processing error.")

        return {
            "status": record["status"],
            "job_id": record["id"],
            "query": record["query"],
            "analysis": record["result"],
            "file_processed": record["original_filename"],
            "created_at": record["created_at"],
            "updated_at": record["updated_at"],
        }
    except HTTPException:
        raise
    except Exception as exc:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass
        raise HTTPException(status_code=500, detail=f"Error processing financial document: {exc}") from exc
    finally:
        if not wait:
            # The worker handles cleanup and event lifecycle for async jobs.
            pass
        else:
            job_events.pop(job_id, None)


@app.get("/jobs/{job_id}")
async def get_job(job_id: str) -> Dict[str, Any]:
    record = _fetch_job(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Job not found.")

    return {
        "job_id": record["id"],
        "status": record["status"],
        "query": record["query"],
        "file_processed": record["original_filename"],
        "analysis": record["result"],
        "error": record["error"],
        "created_at": record["created_at"],
        "updated_at": record["updated_at"],
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
