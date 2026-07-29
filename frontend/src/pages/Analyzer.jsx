import { useRef, useState } from "react";
import { marked } from "marked";
import { apiUrl } from "../api.js";

const MAX_FILES = 5;

export default function Analyzer() {
  const [files, setFiles] = useState([]);
  const [drag, setDrag] = useState(false);
  const [running, setRunning] = useState(false);
  const [report, setReport] = useState(null);
  const [cards, setCards] = useState([]);
  const [open, setOpen] = useState(null); // index of expanded card
  const [error, setError] = useState(null);
  const inputRef = useRef(null);

  const addFiles = (list) => {
    const pdfs = [...list].filter(
      (f) => f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf")
    );
    setFiles((prev) => {
      const names = new Set(prev.map((f) => f.name));
      const merged = [...prev, ...pdfs.filter((f) => !names.has(f.name))];
      return merged.slice(0, MAX_FILES);
    });
  };

  const run = async () => {
    setRunning(true);
    setError(null);
    setReport(null);
    setCards([]);
    setOpen(null);
    try {
      const form = new FormData();
      files.forEach((f) => form.append("files", f));
      const r = await fetch(apiUrl("/api/screen"), { method: "POST", body: form });
      if (!r.ok) throw new Error(`Backend returned ${r.status}`);
      const json = await r.json();
      setReport(json.report);
      setCards(Array.isArray(json.cards) ? json.cards : []);
    } catch (e) {
      setError(e.message);
    } finally {
      setRunning(false);
    }
  };

  const detailFor = (name) => extractDetail(report, name);

  return (
    <>
      <h1 className="page-title">Resume analyzer</h1>
      <p className="page-sub">
        Upload up to {MAX_FILES} PDF resumes for scoring against open roles
      </p>

      <div
        className={`dropzone ${drag ? "drag" : ""}`}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
          addFiles(e.dataTransfer.files);
        }}
      >
        <i className="ti ti-cloud-upload" aria-hidden="true" />
        <p>Drag resumes here or click to browse</p>
        <p className="hint">PDF only · max {MAX_FILES} files</p>
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf"
          multiple
          hidden
          onChange={(e) => {
            addFiles(e.target.files);
            e.target.value = "";
          }}
        />
      </div>

      {files.length > 0 && (
        <div className="chips">
          {files.map((f) => (
            <span className="chip" key={f.name}>
              <i className="ti ti-file" aria-hidden="true" />
              {f.name}
              <button
                aria-label={`Remove ${f.name}`}
                onClick={() =>
                  setFiles((prev) => prev.filter((x) => x.name !== f.name))
                }
              >
                <i className="ti ti-x" aria-hidden="true" />
              </button>
            </span>
          ))}
        </div>
      )}

      <button
        className="btn-primary"
        disabled={files.length === 0 || running}
        onClick={run}
      >
        {running ? "Screening…" : "Run screening"}
      </button>

      {running && (
        <div className="loading">
          <div className="spinner" />
          Screening in progress — this usually takes a minute or two.
        </div>
      )}

      {error && (
        <div className="error-box">
          Screening failed — {error}. Check the backend is running and try
          again.
        </div>
      )}

      {cards.length > 0 && (
        <>
          <div className="results-head">
            <p className="results-title">
              {cards.length} candidate{cards.length > 1 ? "s" : ""} screened
            </p>
            <p className="results-hint">Click a card for full detail</p>
          </div>
          <div className="score-cards">
            {cards
              .slice()
              .sort((a, b) => (b.fit_score ?? 0) - (a.fit_score ?? 0))
              .map((c, i) => (
                <ScoreCard
                  key={i}
                  c={c}
                  isOpen={open === i}
                  onToggle={() => setOpen(open === i ? null : i)}
                  detailHtml={open === i ? detailFor(c.name) : null}
                />
              ))}
          </div>
        </>
      )}

      {cards.length === 0 && report && (
        <div className="card" style={{ marginTop: 16 }}>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: 4,
            }}
          >
            <p style={{ fontWeight: 600, fontSize: 15 }}>Screening report</p>
            <span className="badge green">Complete</span>
          </div>
          <div
            className="sc-report"
            dangerouslySetInnerHTML={{ __html: marked.parse(report) }}
          />
        </div>
      )}
    </>
  );
}

const BAND_CLASS = {
  "Fast-track": "band-fast",
  Shortlisted: "band-short",
  Hold: "band-hold",
  Reject: "band-reject",
};

function ScoreCard({ c, isOpen, onToggle, detailHtml }) {
  return (
    <div className={`card score-card ${isOpen ? "open" : ""}`}>
      <button
        className="score-card-head"
        onClick={onToggle}
        aria-expanded={isOpen}
      >
        <div className="sc-left">
          <p className="sc-name">{c.name}</p>
          {c.role && <p className="sc-role">{c.role}</p>}
        </div>
        <div className="sc-right">
          {typeof c.fit_score === "number" && (
            <span className="sc-score">{c.fit_score}</span>
          )}
          {c.band && (
            <span className={`sc-band ${BAND_CLASS[c.band] || ""}`}>
              {c.band}
            </span>
          )}
          <i
            className={`ti ti-chevron-down sc-chevron ${isOpen ? "up" : ""}`}
            aria-hidden="true"
          />
        </div>
      </button>

      {!isOpen && (
        <div className="sc-preview">
          {c.matched_skills?.slice(0, 6).map((s) => (
            <span className="sc-skill matched" key={s}>
              {s}
            </span>
          ))}
          {c.matched_skills?.length > 6 && (
            <span className="sc-more">+{c.matched_skills.length - 6}</span>
          )}
        </div>
      )}

      {isOpen && (
        <div className="sc-detail">
          {c.summary && <p className="sc-summary">{c.summary}</p>}

          <div className="sc-meta-row">
            {c.email && (
              <span>
                <i className="ti ti-mail" aria-hidden="true" /> {c.email}
              </span>
            )}
            {c.phone && (
              <span>
                <i className="ti ti-phone" aria-hidden="true" /> {c.phone}
              </span>
            )}
            {c.experience_years != null && (
              <span>
                <i className="ti ti-briefcase" aria-hidden="true" />{" "}
                {c.experience_years} yrs exp
              </span>
            )}
          </div>

          {c.matched_skills?.length > 0 && (
            <div className="sc-skills">
              <span className="sc-skills-label">Matched</span>
              {c.matched_skills.map((s) => (
                <span className="sc-skill matched" key={s}>
                  {s}
                </span>
              ))}
            </div>
          )}

          {c.missing_skills?.length > 0 && (
            <div className="sc-skills">
              <span className="sc-skills-label">Gaps</span>
              {c.missing_skills.map((s) => (
                <span className="sc-skill missing" key={s}>
                  {s}
                </span>
              ))}
            </div>
          )}

          {hasStructuredDetail(c) ? (
            <div className="sc-report">
              {c.scores_line && (
                <p>
                  <strong>Scores:</strong> {c.scores_line}
                </p>
              )}
              {c.verdict && (
                <p>
                  <strong>Verdict:</strong> {c.verdict}
                </p>
              )}
              {(c.interview_questions?.technical?.length > 0 ||
                c.interview_questions?.behavioral?.length > 0) && (
                <>
                  <p>
                    <strong>Interview Questions</strong>
                  </p>
                  {c.interview_questions?.technical?.length > 0 && (
                    <>
                      <p>
                        <em>Technical</em>
                      </p>
                      <ol>
                        {c.interview_questions.technical.map((q, i) => (
                          <li key={i}>{q}</li>
                        ))}
                      </ol>
                    </>
                  )}
                  {c.interview_questions?.behavioral?.length > 0 && (
                    <>
                      <p>
                        <em>Behavioral</em>
                      </p>
                      <ol>
                        {c.interview_questions.behavioral.map((q, i) => (
                          <li key={i}>{q}</li>
                        ))}
                      </ol>
                    </>
                  )}
                </>
              )}
            </div>
          ) : (
            detailHtml && (
              <div
                className="sc-report"
                dangerouslySetInnerHTML={{ __html: detailHtml }}
              />
            )
          )}
        </div>
      )}
    </div>
  );
}

// True when the card carries structured detail fields (new JSON format).
function hasStructuredDetail(c) {
  return Boolean(
    c.verdict ||
      c.scores_line ||
      c.interview_questions?.technical?.length ||
      c.interview_questions?.behavioral?.length
  );
}

/**
 * Pull one candidate's section out of the full markdown report and render it
 * to HTML. Report sections start with a heading like:
 *   ### **Meera Krishnan** — Machine Learning Engineer — 100/100
 * We find the heading containing the candidate name and take everything up to
 * the next ### heading or a --- divider. Returns HTML string, or "" if not found.
 */
function extractDetail(report, name) {
  if (!report || !name) return "";
  const lines = report.split("\n");
  const nameLC = name.toLowerCase();
  const firstLC = name.split(" ")[0].toLowerCase();

  // A "candidate detail header" is a bold line formatted like
  // **Name** — Role — Score. This is where the per-candidate detail
  // (scores, verdict, interview questions) actually lives.
  const isBoldCandidateHeader = (l) => {
    const t = l.trim();
    return /^\*\*[A-Z]/.test(t) && /[—–-]/.test(t) && !/:/.test(t.slice(0, 40));
  };
  // Any header (### or bold candidate) ends a section.
  const isHeader = (l) => {
    const t = l.trim();
    return t.startsWith("###") || isBoldCandidateHeader(l);
  };
  const namesThis = (l) => {
    const lc = l.toLowerCase();
    return lc.includes(nameLC) || lc.includes(firstLC);
  };

  // Prefer a bold candidate header that names this person (the detail block).
  // Fall back to any header that names them.
  let start = -1;
  for (let i = 0; i < lines.length; i++) {
    if (isBoldCandidateHeader(lines[i]) && namesThis(lines[i])) {
      start = i;
      break;
    }
  }
  if (start === -1) {
    for (let i = 0; i < lines.length; i++) {
      if (isHeader(lines[i]) && namesThis(lines[i])) {
        start = i;
        break;
      }
    }
  }
  if (start === -1) return "";

  let end = lines.length;
  for (let i = start + 1; i < lines.length; i++) {
    if (isHeader(lines[i])) {
      end = i;
      break;
    }
  }

  // Drop the heading line itself (the card already shows name/role/score).
  let chunk = lines.slice(start + 1, end);
  // Remove **Matched:** / **Gaps:** lines — the card already shows these as chips.
  chunk = chunk.filter((l) => {
    const t = l.trim();
    return !/^\*\*(Matched|Gaps)\s*:?\*\*/i.test(t);
  });
  // Trim leading/trailing blanks and --- dividers.
  const junk = (s) => s.trim() === "" || s.trim() === "---";
  while (chunk.length && junk(chunk[chunk.length - 1])) chunk.pop();
  while (chunk.length && junk(chunk[0])) chunk.shift();
  // If a trailing "That's the batch"-style wrap-up leaked in (last candidate),
  // cut it at the wrap-up sentence.
  const wrapIdx = chunk.findIndex((l) => /^That'?s the batch/i.test(l.trim()));
  if (wrapIdx !== -1) chunk = chunk.slice(0, wrapIdx);
  while (chunk.length && junk(chunk[chunk.length - 1])) chunk.pop();

  return marked.parse(chunk.join("\n"));
}