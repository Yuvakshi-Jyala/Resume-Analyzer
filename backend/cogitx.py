"""
CogitX workflow client for the Resume Screening workflow.

Confirmed from the export docs + a real response:
  - Auth: header-based x-client-id / x-client-secret (NO token exchange)
  - Trigger: POST /exports/rest-api/{export_id}/jobs
  - Poll:    GET  /exports/rest-api/{export_id}/jobs/{runId}
  - Response wraps in {statusCode, message, data:{...}}. Everything real is
    under data. Sync completions come back with data.isCompleted=true inline;
    async ones come back with data.accepted=true -> poll until isCompleted.
  - Final text: data.output.workflow_response.content
    (fallbacks: data.output.variables.text / .message)
  - Conditional routing keys off the input: files present -> screening branch,
    otherwise the KPI / hiring-status branch.
"""
import base64
import os
import time

import httpx

BASE_URL = os.getenv("COGITX_BASE_URL", "https://platform.cogitx.ai").rstrip("/")
EXPORT_ID = os.getenv("COGITX_EXPORT_ID", "")
CLIENT_ID = os.getenv("COGITX_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("COGITX_CLIENT_SECRET", "")
KPI_TRIGGER_MESSAGE = os.getenv("KPI_TRIGGER_MESSAGE", "show kpi dashboard")

TRIGGER_URL = f"{BASE_URL}/exports/rest-api/{EXPORT_ID}/jobs"
POLL_URL = f"{BASE_URL}/exports/rest-api/{EXPORT_ID}/jobs/{{run_id}}"

POLL_INTERVAL = 3        # seconds between async status polls
POLL_TIMEOUT = 300       # give up after this many seconds


def _headers() -> dict:
    if not (CLIENT_ID and CLIENT_SECRET):
        raise RuntimeError(
            "COGITX_CLIENT_ID / COGITX_CLIENT_SECRET not set. "
            "Fill them in backend/.env before starting the backend."
        )
    return {
        "Content-Type": "application/json",
        "x-client-id": CLIENT_ID,
        "x-client-secret": CLIENT_SECRET,
    }


def _trigger(body: dict) -> dict:
    """POST the job, handle sync-inline vs async-poll, return the `data` object."""
    if not EXPORT_ID:
        raise RuntimeError("COGITX_EXPORT_ID not set.")
    with httpx.Client(timeout=httpx.Timeout(30.0, read=300.0)) as client:
        r = client.post(TRIGGER_URL, json=body, headers=_headers())
        r.raise_for_status()
        data = r.json().get("data", {})

        # Sync: completed within the wait window.
        if data.get("isCompleted"):
            return data

        # Async: accepted for background processing -> poll runId.
        run_id = data.get("runId")
        if data.get("accepted") and run_id:
            return _poll(client, run_id)

        # Neither flag but we have a runId -> poll anyway to be safe.
        if run_id:
            return _poll(client, run_id)

        raise RuntimeError(f"Unexpected trigger response (no isCompleted/runId): {list(data)}")


def _poll(client: httpx.Client, run_id: str) -> dict:
    deadline = time.time() + POLL_TIMEOUT
    url = POLL_URL.format(run_id=run_id)
    while time.time() < deadline:
        time.sleep(POLL_INTERVAL)
        r = client.get(url, headers=_headers())
        r.raise_for_status()
        data = r.json().get("data", {})
        if data.get("isCompleted"):
            return data
    raise TimeoutError(f"Job {run_id} did not complete within {POLL_TIMEOUT}s")


def _extract_text(data: dict) -> str:
    """Pull the final agent text out of a completed job's `data` object."""
    if not data.get("success", True):
        raise RuntimeError(f"Workflow reported failure: {data.get('error')}")

    output = data.get("output", {}) or {}

    # Preferred: the clean final text.
    wr = output.get("workflow_response", {})
    if isinstance(wr, dict) and isinstance(wr.get("content"), str) and wr["content"].strip():
        return wr["content"]

    # Fallbacks: variables.text / variables.message.
    variables = output.get("variables", {}) or {}
    for key in ("text", "message"):
        val = variables.get(key)
        if isinstance(val, str) and val.strip():
            return val

    raise ValueError(
        f"Could not locate output text. output keys={list(output)}, "
        f"variables keys={list(variables)}"
    )


def run_kpi() -> str:
    """No files -> conditional ELSE branch -> hiring status summary text."""
    data = _trigger({"text": KPI_TRIGGER_MESSAGE})
    return _extract_text(data)


def run_screening(files: list[tuple[str, bytes]]) -> dict:
    """
    Resumes present -> conditional IF branch -> full screening pipeline.

    Returns {report, candidates, results}:
      - report:     the markdown candidate report (always present)
      - candidates: parsed profiles (name, email, skills, experience, ...)
      - results:    scoring per candidate (fit_score, band, rubric_breakdown, ...)

    candidates/results default to [] if the workflow didn't emit them, so the
    frontend degrades to markdown-only automatically.

    files: list of (filename, raw_bytes). The JSON API wants base64-encoded
    files (per the export docs), so we encode here.
    """
    encoded = [
        {
            "filename": name,
            "mimeType": "application/pdf",
            "base64": base64.b64encode(blob).decode("ascii"),
        }
        for name, blob in files
    ]
    data = _trigger({
        "text": "Screen the attached resumes and produce the candidate report.",
        "files": encoded,
    })
    report = _extract_text(data)

    output = data.get("output", {}) or {}
    candidates = output.get("candidates")
    results = output.get("results")
    candidates = candidates if isinstance(candidates, list) else []
    results = results if isinstance(results, list) else []
    return {
        "report": report,
        "cards": _merge_cards(results, candidates),
    }


def _merge_cards(results: list, candidates: list) -> list:
    """Join scoring (results) with profile (candidates) by candidate_name into
    a flat per-candidate card the frontend can render directly. Scoring drives
    the list; profile fields are looked up and attached where the name matches."""
    by_name = {}
    for c in candidates:
        if isinstance(c, dict) and c.get("candidate_name"):
            by_name[c["candidate_name"]] = c

    cards = []
    for r in results:
        if not isinstance(r, dict):
            continue
        name = r.get("candidate_name", "")
        prof = by_name.get(name, {})
        cards.append({
            "name": name,
            "role": r.get("matched_role") or prof.get("role_applied") or "",
            "email": prof.get("email"),
            "phone": prof.get("phone"),
            "fit_score": r.get("fit_score"),
            "band": r.get("band"),
            "matched_skills": r.get("matched_skills") or [],
            "missing_skills": r.get("missing_skills") or [],
            "summary": r.get("summary_reason") or "",
            "experience_years": prof.get("total_experience_years"),
        })
    return cards
