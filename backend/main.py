import json
import os
import re

from dotenv import load_dotenv

load_dotenv()  # read backend/.env before anything reads os.getenv

from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware

import cogitx

# Comma-separated list of allowed frontend origins. Locally we default to the
# vite dev server; in production set FRONTEND_ORIGINS to the deployed URL(s),
# e.g. "https://your-app.vercel.app".
_default_origins = "http://localhost:5173,http://127.0.0.1:5173"
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv("FRONTEND_ORIGINS", _default_origins).split(",")
    if o.strip()
]

app = FastAPI(title="Resume Screening UI backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# The KPI agent emits a markdown table + a ```chart block. The table is the
# richer source (all 5 columns), so parse it first and fall back to the chart.

# Column header -> the Dashboard's expected field name.
_COL_MAP = {
    "received": "applications_received",
    "cap": "cap",
    "shortlisted": "shortlisted",
    "calls scheduled": "calls_scheduled",
    "calls completed": "calls_completed",
}


def _norm(h: str) -> str:
    return h.strip().lower()


def parse_role_breakdown(text: str):
    """Parse the 'Quick View' markdown table into role objects the UI expects.
    Falls back to the ```chart block if no table is found."""
    roles = _parse_markdown_table(text)
    if roles:
        return roles
    return _parse_chart_block(text) or []


def _parse_markdown_table(text: str):
    lines = [ln for ln in text.splitlines() if ln.strip().startswith("|")]
    if len(lines) < 2:
        return None

    def cells(row):
        return [c.strip() for c in row.strip().strip("|").split("|")]

    header = [_norm(c) for c in cells(lines[0])]
    # lines[1] is the |---|---| separator; data starts at lines[2].
    out = []
    for row in lines[2:]:
        vals = cells(row)
        if len(vals) != len(header):
            continue
        rec = {"role": vals[0]}
        for h, v in zip(header[1:], vals[1:]):
            field = _COL_MAP.get(h)
            if not field:
                continue
            try:
                rec[field] = int(v)
            except ValueError:
                rec[field] = 0
        # ensure all numeric fields exist so the frontend never gets undefined
        for field in ("applications_received", "shortlisted", "calls_scheduled",
                      "calls_completed", "cap"):
            rec.setdefault(field, 0)
        out.append(rec)
    return out or None


def _parse_chart_block(text: str):
    """Fallback: read the fenced ```chart {...} ``` JSON block."""
    m = re.search(r"```chart\s*(\{.*?\})\s*```", text, re.DOTALL)
    if not m:
        return None
    try:
        chart = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    out = []
    for d in chart.get("data", []):
        out.append({
            "role": d.get("role", ""),
            "applications_received": d.get("applications_received", 0),
            "shortlisted": d.get("shortlisted", 0),
            "calls_scheduled": 0,
            "calls_completed": 0,
            "cap": 0,
        })
    return out or None


def parse_interviews(text: str):
    """Pull '- {date} at {time} — {name} ({role})' lines from the summary."""
    pattern = re.compile(
        r"[-*]\s*(\d{4}-\d{2}-\d{2})\s+at\s+([\d: ]+[APap][Mm])\s*[—-]+\s*(.+?)\s*\((.+?)\)"
    )
    return [
        {"date": d, "time": t.strip(), "name": n.strip(), "role": r.strip()}
        for d, t, n, r in pattern.findall(text)
    ]

def parse_interviews(text: str):
    """Pull '- {date} at {time} — {name} ({role})' lines from the summary."""
    pattern = re.compile(
        r"[-*]\s*(\d{4}-\d{2}-\d{2})\s+at\s+([\d: ]+[APap][Mm])\s*[—-]+\s*(.+?)\s*\((.+?)\)"
    )
    return [
        {"date": d, "time": t.strip(), "name": n.strip(), "role": r.strip()}
        for d, t, n, r in pattern.findall(text)
    ]

# vvv ADD THE TWO NEW THINGS HERE vvv

_CANDIDATE_LINE_RE = re.compile(
    r"^-\s*(?P<role>[^|]+)\|\s*(?P<name>[^|]+)\|\s*(?P<status>[^|]+?)"
    r"(?:\s*\|\s*(?P<idate>\d{4}-\d{2}-\d{2})\s+at\s+(?P<itime>[^|]+?))?"
    r"(?:\s*\|\s*score:\s*(?P<score>[\d.]+))?\s*$"
)


def parse_all_candidates(text: str):
    m = re.search(r"###\s*All Candidates\s*\n(.*?)(?=\n###|\Z)", text, re.DOTALL)
    if not m:
        return {}
    by_role: dict[str, list] = {}
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line:
            continue
        cm = _CANDIDATE_LINE_RE.match(line)
        if not cm:
            continue
        role = cm.group("role").strip()
        score_raw = cm.group("score")
        by_role.setdefault(role, []).append({
            "name": cm.group("name").strip(),
            "status": cm.group("status").strip(),
            "interview_date": cm.group("idate"),
            "interview_time": (cm.group("itime") or "").strip() or None,
            "score": float(score_raw) if score_raw else None,
        })
    return by_role

# ^^^ END ADDITION ^^^
@app.get("/api/kpi")
def kpi():
    text = cogitx.run_kpi()
    return {
        "raw_text": text,
        "roles": parse_role_breakdown(text) or [],
        "interviews": parse_interviews(text),
        "candidates_by_role": parse_all_candidates(text),
    }


@app.post("/api/screen")
async def screen(files: list[UploadFile] = File(...)):
    blobs = [(f.filename, await f.read()) for f in files[:5]]
    result = cogitx.run_screening(blobs)
    # result = {report, candidates, results}
    return result
