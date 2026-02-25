# Financial Document Analyzer

This project started as a buggy CrewAI-based financial document analyzer.  
I debugged it end-to-end, cleaned up the prompts, and added a queue + database flow so it behaves like a usable backend service.

The API accepts PDF uploads, runs analysis through CrewAI agents, and returns structured results with job tracking.

## What I Found and Fixed

### 1) Deterministic bugs

- `agents.py` had `llm = llm`, which fails immediately.
  - Fixed by introducing a proper agent factory (`create_agents`) and reading model config from environment variables.

- Agent/task wiring was incorrect in multiple places.
  - Fixed imports and object creation flow so agents and tasks are created in a predictable, testable way.

- `tools.py` used undefined PDF logic (`Pdf`) and async functions in places where synchronous execution was expected.
  - Replaced with reliable PDF parsing using `pypdf.PdfReader`.

- `main.py` had naming collisions and inconsistent Crew kickoff inputs.
  - Separated concerns cleanly and now pass both `query` and `document_excerpt` to Crew kickoff.

- File handling and failure paths were fragile.
  - Added safer validation, cleanup, and consistent error responses.

### 2) Inefficient / unsafe prompts

The original prompts encouraged hallucinations, fake links, contradictions, and low-quality analysis.  
I rewrote prompts to be practical and grounded:

- Use only evidence from the uploaded document.
- Explicitly say when something is missing (`Not stated in the document`).
- Return structured output (Summary, Key Metrics, Risks, Next Steps).
- Include a short non-advisory disclaimer.

### 3) Bonus improvements

- Queue worker model:
  - Added an internal async queue for concurrent request handling (`queued -> processing -> completed/failed`).

- Database integration:
  - Added SQLite persistence (`analysis.db`) to store job metadata, status, results, and errors.

## Current Project Structure

- `main.py`: FastAPI app, queue worker lifecycle, DB operations, API routes
- `agents.py`: CrewAI agent factory
- `task.py`: CrewAI task factory and prompt templates
- `tools.py`: PDF extraction + normalization helpers
- `data/`: temporary uploaded files
- `analysis.db`: runtime SQLite database

## Setup

### 1) Install dependencies

```bash
pip install -r requirements.txt
```

### 2) Configure environment variables

Windows (PowerShell):

```powershell
$env:OPENAI_API_KEY="your_api_key_here"
$env:CREWAI_MODEL="gpt-4o-mini"
```

Windows (cmd):

```cmd
set OPENAI_API_KEY=your_api_key_here
set CREWAI_MODEL=gpt-4o-mini
```

### 3) Run the server

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Usage

### Synchronous request (wait for result)

```bash
curl -X POST "http://localhost:8000/analyze" ^
  -F "file=@data/TSLA-Q2-2025-Update.pdf" ^
  -F "query=Summarize revenue growth and major risks" ^
  -F "wait=true"
```

### Asynchronous request (queue job and poll later)

```bash
curl -X POST "http://localhost:8000/analyze" ^
  -F "file=@data/TSLA-Q2-2025-Update.pdf" ^
  -F "query=Focus on cash flow and debt signals" ^
  -F "wait=false"
```

Then check status:

```bash
curl "http://localhost:8000/jobs/<job_id>"
```

## API Documentation

### `GET /`

Basic health check.

Response:

```json
{
  "message": "Financial Document Analyzer API is running"
}
```

### `POST /analyze`

Upload and analyze a PDF.

Form fields:
- `file` (required): PDF file only
- `query` (optional): analysis prompt
- `wait` (optional, default `true`):
  - `true`: return analysis directly
  - `false`: return `job_id` and process in queue

Example success (`wait=true`):

```json
{
  "status": "completed",
  "job_id": "9df5...e5d",
  "query": "Summarize revenue growth and major risks",
  "analysis": "...",
  "file_processed": "TSLA-Q2-2025-Update.pdf",
  "created_at": "2026-02-25T14:30:00+00:00",
  "updated_at": "2026-02-25T14:30:08+00:00"
}
```

Example success (`wait=false`):

```json
{
  "status": "queued",
  "job_id": "9df5...e5d",
  "query": "Focus on cash flow and debt signals"
}
```

### `GET /jobs/{job_id}`

Get job status/result by ID.

Response shape:

```json
{
  "job_id": "9df5...e5d",
  "status": "queued|processing|completed|failed",
  "query": "...",
  "file_processed": "...",
  "analysis": "...",
  "error": null,
  "created_at": "...",
  "updated_at": "..."
}
```

## Notes

- Only PDFs are accepted (`application/pdf`).
- Uploaded files are deleted after processing.
- Output is document-based analysis, not financial advice.
