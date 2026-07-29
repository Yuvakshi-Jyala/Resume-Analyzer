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
import logging
import os
import time

import httpx

logger = logging.getLogger("cogitx")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("[cogitx] %(levelname)s %(message)s"))
    logger.addHandler(_h)
logger.setLevel(logging.INFO)

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


def run_screening(files: list[tuple[str, bytes]]) -> dict:
    """
    Resumes present -> conditional IF branch -> full screening pipeline.

    Returns {report, cards}. Handles two response shapes:
      1. New: agent_2 outputs JSON {report_markdown, candidates:[...]} — read directly.
      2. Old: agent_2 outputs prose text — parse cards out of the report text.
    This lets the backend work before and after the workflow is switched to JSON.

    files: list of (filename, raw_bytes), base64-encoded for the JSON API.
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

    # The final output content is either a JSON object/string (new format) or
    # plain prose (old format). Grab the raw content first.
    raw = _extract_content(data)

    # --- DIAGNOSTIC LOGGING ---
    output = data.get("output", {}) or {}
    logger.info("SCREEN output keys: %s", list(output.keys()))
    logger.info("raw content type: %s", type(raw).__name__)
    if isinstance(raw, str):
        logger.info("raw content preview: %s", raw[:300])
    elif isinstance(raw, dict):
        logger.info("raw content keys: %s", list(raw.keys()))
    # --- END LOGGING ---

    # Try the new JSON format.
    parsed = _try_parse_json(raw)
    # The CogitX JSON Output node wraps its payload as {"result": {...}, "timestamp": ...}.
    # Unwrap to reach the actual {report_markdown, candidates}.
    if isinstance(parsed, dict) and "result" in parsed and "candidates" not in parsed:
        inner = parsed["result"]
        if isinstance(inner, str):
            inner = _try_parse_json(inner)
        if isinstance(inner, dict):
            parsed = inner
            logger.info("unwrapped result -> keys: %s", list(parsed.keys()))

    if isinstance(parsed, dict):
        logger.info("parsed JSON keys: %s", list(parsed.keys()))
        logger.info("candidates type: %s", type(parsed.get("candidates")).__name__)
        logger.info("report_markdown present: %s, len: %s",
                    "report_markdown" in parsed,
                    len(parsed.get("report_markdown") or "") if isinstance(parsed.get("report_markdown"), str) else "n/a")
    if isinstance(parsed, dict) and ("candidates" in parsed or "report_markdown" in parsed):
        # CogitX's JSON Output template can stringify nested arrays/objects,
        # so candidates may arrive as a JSON string — un-stringify if needed.
        cand = parsed.get("candidates")
        if isinstance(cand, str):
            cand = _try_parse_json_list(cand)
        cand = cand if isinstance(cand, list) else []
        if cand:
            logger.info("first candidate keys: %s", list(cand[0].keys()) if isinstance(cand[0], dict) else "not-dict")

        report = parsed.get("report_markdown") or ""
        if not isinstance(report, str):
            report = str(report)

        if cand:
            cards = [_card_from_json(c) for c in cand if isinstance(c, dict)]
            return {"report": report, "cards": cards}
        # No usable candidates but we have a report -> fall through to report
        # parsing below using `report` as the prose source.
        raw = report

    # Old format: raw is the prose report. Try structured side-channel first,
    # then fall back to parsing the report text.
    report = raw if isinstance(raw, str) else ""
    output = data.get("output", {}) or {}
    variables = output.get("variables", {}) or {}
    results = variables.get("results")
    if not isinstance(results, list):
        results = output.get("results")
    candidates = variables.get("candidates")
    if not isinstance(candidates, list):
        candidates = output.get("candidates")
    results = results if isinstance(results, list) else []
    candidates = candidates if isinstance(candidates, list) else []
    cards = _merge_cards(results, candidates)
    if not cards and report:
        cards = _cards_from_report(report)

    return {"report": report, "cards": cards}


def _extract_content(data: dict):
    """Return the final output content (may be str, dict, or JSON string)."""
    if not data.get("success", True):
        raise RuntimeError(f"Workflow reported failure: {data.get('error')}")
    output = data.get("output", {}) or {}
    wr = output.get("workflow_response", {})
    if isinstance(wr, dict) and wr.get("content") is not None:
        return wr["content"]
    variables = output.get("variables", {}) or {}
    for key in ("text", "message"):
        if variables.get(key) is not None:
            return variables[key]
    raise ValueError(f"Could not locate output content. output keys={list(output)}")


def _try_parse_json(raw):
    """If raw is a dict, return it. If it's a JSON string (possibly fenced),
    parse and return it. Otherwise return None."""
    import json
    import re
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return None
    s = raw.strip()
    # strip ```json ... ``` fences if present
    m = re.match(r"^```(?:json)?\s*(.+?)\s*```$", s, re.DOTALL)
    if m:
        s = m.group(1).strip()
    if not (s.startswith("{") and s.endswith("}")):
        return None
    try:
        return json.loads(s)
    except (ValueError, TypeError):
        return None


def _try_parse_json_list(raw):
    """Parse a JSON string that should contain a list; return [] on failure."""
    import json
    import re
    if isinstance(raw, list):
        return raw
    if not isinstance(raw, str):
        return []
    s = raw.strip()
    m = re.match(r"^```(?:json)?\s*(.+?)\s*```$", s, re.DOTALL)
    if m:
        s = m.group(1).strip()
    try:
        val = json.loads(s)
        return val if isinstance(val, list) else []
    except (ValueError, TypeError):
        return []


def _card_from_json(c: dict) -> dict:
    """Map a candidate object from agent_2's JSON output to a frontend card."""
    q = c.get("interview_questions") or {}
    return {
        "name": c.get("name", ""),
        "role": c.get("role", ""),
        "email": c.get("email"),
        "phone": c.get("phone"),
        "fit_score": c.get("fit_score"),
        "band": c.get("band"),
        "matched_skills": c.get("matched_skills") or [],
        "missing_skills": c.get("missing_skills") or [],
        "summary": c.get("summary") or "",
        "experience_years": c.get("experience_years"),
        "scores_line": c.get("scores_line") or "",
        "verdict": c.get("verdict") or "",
        "interview_questions": {
            "technical": q.get("technical") or [],
            "behavioral": q.get("behavioral") or [],
        },
    }


def run_kpi() -> str:
    """No files -> conditional ELSE branch -> hiring status summary text."""
    data = _trigger({"text": KPI_TRIGGER_MESSAGE})
    raw = _extract_content(data)
    return raw if isinstance(raw, str) else str(raw)


def _cards_from_report(report: str) -> list:
    """Fallback card builder: parse per-candidate cards out of the markdown
    report when the workflow didn't return structured data.

    Looks for detail blocks headed by:  **Name** — Role — Score/100
    and pulls Matched/Gaps/Verdict from the following lines. Also picks up
    non-shortlisted candidates from a '### Not shortlisted' bullet list.
    """
    import re

    cards = []
    lines = report.split("\n")

    # 1) Shortlisted candidates: **Name** — Role — NN/100 (or NN)
    header_re = re.compile(
        r"^\*\*(?P<name>[^*]+?)\*\*\s*[—–-]\s*(?P<role>.+?)\s*[—–-]\s*(?P<score>\d+(?:\.\d+)?)\s*(?:/\s*100)?\s*$"
    )
    matched_re = re.compile(r"^\*\*Matched:?\*\*\s*(.+)$", re.IGNORECASE)
    gaps_re = re.compile(r"^\*\*Gaps:?\*\*\s*(.+)$", re.IGNORECASE)
    verdict_re = re.compile(r"^\*\*Verdict:?\*\*\s*(.+)$", re.IGNORECASE)

    def split_skills(s: str) -> list:
        # strip trailing markdown spaces, split on commas
        return [x.strip() for x in s.replace("  ", " ").split(",") if x.strip()]

    def band_from_score(score: float) -> str:
        if score >= 85:
            return "Fast-track"
        if score >= 70:
            return "Shortlisted"
        if score >= 50:
            return "Hold"
        return "Reject"

    seen = set()
    for i, line in enumerate(lines):
        m = header_re.match(line.strip())
        if not m:
            continue
        name = m.group("name").strip()
        if name.lower() in seen:
            continue
        seen.add(name.lower())
        role = m.group("role").strip()
        score = float(m.group("score"))

        matched, gaps, summary = [], [], ""
        # scan the next ~15 lines for this candidate's fields
        for j in range(i + 1, min(i + 16, len(lines))):
            t = lines[j].strip()
            if header_re.match(t):
                break
            mm = matched_re.match(t)
            if mm:
                matched = split_skills(mm.group(1))
            gm = gaps_re.match(t)
            if gm:
                g = gm.group(1).strip()
                gaps = [] if g.lower() in ("none", "none.") else split_skills(g)
            vm = verdict_re.match(t)
            if vm:
                summary = vm.group(1).strip()

        cards.append({
            "name": name,
            "role": role,
            "email": None,
            "phone": None,
            "fit_score": int(score) if score.is_integer() else score,
            "band": band_from_score(score),
            "matched_skills": matched,
            "missing_skills": gaps,
            "summary": summary,
            "experience_years": None,
        })

    return cards


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