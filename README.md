# CogitX AI — Resume Screening UI

Two-page internal tool: KPI dashboard + resume analyzer, wired live to the
CogitX Resume Screening workflow through a thin FastAPI proxy.

## Setup

Backend:
    cd backend
    copy .env.example .env        # then fill in CLIENT_ID / CLIENT_SECRET
    pip install -r requirements.txt
    uvicorn main:app --reload --port 8000

Frontend (separate terminal):
    cd frontend
    npm install
    npm run dev

Open http://localhost:5173

## Configuration (backend/.env)

- COGITX_BASE_URL     prefix; code appends /exports/rest-api/{id}/jobs
- COGITX_EXPORT_ID    the Resume Screening workflow export id
- COGITX_CLIENT_ID    x-client-id header value
- COGITX_CLIENT_SECRET x-client-secret header value
- KPI_TRIGGER_MESSAGE text sent on the KPI call (routes to hiring-status branch)

## How it maps to the workflow

- GET /api/kpi -> POSTs the KPI trigger text (no files) -> conditional ELSE
  branch -> Hiring Status agent. Backend parses the markdown table + interview
  lines out of the text; the frontend renders stat cards, the bar chart, and
  the interviews list.
- POST /api/screen -> uploads up to 5 PDFs (base64) -> conditional IF branch ->
  screening pipeline -> candidate report text, rendered as markdown.

## Structure

    backend/
      main.py       endpoints + KPI text parsing
      cogitx.py     CogitX transport (auth, trigger, sync/async poll, parse)
    frontend/
      src/App.jsx             sidebar shell
      src/pages/Dashboard.jsx
      src/pages/Analyzer.jsx
      src/styles.css
