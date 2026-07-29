import { useEffect, useState } from "react";
import { apiUrl } from "../api.js";

const SHORT = {
  "Machine Learning Engineer": "MLE",
  "Data Scientist": "DS",
  "Backend Software Engineer": "BE",
  "Product Manager": "PM",
};

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [hovered, setHovered] = useState(null); // role name being hovered in chart

  const load = () => {
    setLoading(true);
    setError(null);
    fetch(apiUrl("/api/kpi"))
      .then((r) => {
        if (!r.ok) throw new Error(`Backend returned ${r.status}`);
        return r.json();
      })
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  if (loading)
    return (
      <>
        <Header onRefresh={load} />
        <div className="loading">
          <div className="spinner" /> Computing hiring status…
        </div>
      </>
    );

  if (error || !data?.roles?.length)
    return (
      <>
        <Header onRefresh={load} />
        <div className="error-box">
          Couldn't load hiring data{error ? ` — ${error}` : ""}. Check the
          backend is running, then refresh.
        </div>
      </>
    );

  const roles = data.roles;
  const totals = roles.reduce(
    (a, r) => ({
      received: a.received + r.applications_received,
      shortlisted: a.shortlisted + r.shortlisted,
      scheduled: a.scheduled + r.calls_scheduled,
      completed: a.completed + r.calls_completed,
    }),
    { received: 0, shortlisted: 0, scheduled: 0, completed: 0 }
  );
  const maxReceived = Math.max(...roles.map((r) => r.applications_received));

  return (
    <>
      <Header onRefresh={load} />

      <div className="stats">
        <Stat label="Applications received" value={totals.received} />
        <Stat label="Shortlisted" value={totals.shortlisted} />
        <Stat label="Calls scheduled" value={totals.scheduled} />
        <Stat label="Calls completed" value={totals.completed} />
      </div>

      <div className="grid-2">
        <div className="card">
          <p style={{ fontWeight: 500, marginBottom: 12 }}>
            Received vs shortlisted by role
          </p>
          <div className="chart-row">
            {roles.map((r) => (
              <div
                className="chart-group"
                key={r.role}
                onMouseEnter={() => setHovered(r.role)}
                onMouseLeave={() => setHovered(null)}
              >
                {hovered === r.role && (
                  <div className="chart-tip">
                    <p className="chart-tip-role">{r.role}</p>
                    <p>
                      <span
                        className="dot"
                        style={{ background: "var(--navy-600)" }}
                      />
                      Received: <b>{r.applications_received}</b>
                    </p>
                    <p>
                      <span
                        className="dot"
                        style={{ background: "var(--slate-400)" }}
                      />
                      Shortlisted: <b>{r.shortlisted}</b>
                    </p>
                  </div>
                )}
                <div
                  className="bar navy"
                  style={{
                    height: `${(r.applications_received / maxReceived) * 100}%`,
                  }}
                />
                <div
                  className="bar slate"
                  style={{
                    height: `${(r.shortlisted / maxReceived) * 100}%`,
                  }}
                />
              </div>
            ))}
          </div>
          <div className="chart-labels">
            {roles.map((r) => (
              <span key={r.role}>{SHORT[r.role] || r.role}</span>
            ))}
          </div>
          <div className="legend">
            <span>
              <span className="dot" style={{ background: "var(--navy-600)" }} />
              Received
            </span>
            <span>
              <span className="dot" style={{ background: "var(--slate-400)" }} />
              Shortlisted
            </span>
          </div>
        </div>

        <div className="card">
          <p style={{ fontWeight: 500, marginBottom: 6 }}>Upcoming interviews</p>
          {data.interviews.length === 0 && (
            <p style={{ color: "var(--text-3)", fontSize: 13 }}>
              No interviews currently scheduled.
            </p>
          )}
          {data.interviews.map((iv, i) => (
            <div className="ivw" key={i}>
              <span className="when">
                {iv.date} · {iv.time}
              </span>
              <span>{iv.name}</span>
              <span className="role">{SHORT[iv.role] || iv.role}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="card" style={{ marginTop: 12 }}>
        <p style={{ fontWeight: 500, marginBottom: 2 }}>Pipeline by role</p>
        <p
          style={{
            fontSize: 12,
            color: "var(--text-3)",
            marginBottom: 16,
          }}
        >
          Capacity used, and how far each role has progressed
        </p>
        <div className="cap-list">
          {roles.map((r) => {
            const pct = r.cap
              ? Math.min((r.applications_received / r.cap) * 100, 100)
              : 0;
            return (
              <div className="cap-row" key={r.role}>
                <div className="cap-head">
                  <span className="cap-role">{r.role}</span>
                  <span className="cap-count">
                    {r.applications_received}
                    {r.cap ? ` / ${r.cap} cap` : ""}
                  </span>
                </div>
                <div className="cap-bar">
                  <div style={{ width: `${pct}%` }} />
                </div>
                <div className="cap-stats">
                  <span>
                    <i
                      className="ti ti-calendar"
                      style={{ color: "var(--amber-tx)" }}
                      aria-hidden="true"
                    />
                    {r.calls_scheduled} scheduled
                  </span>
                  <span>
                    <i
                      className="ti ti-circle-check"
                      style={{ color: "var(--green-tx)" }}
                      aria-hidden="true"
                    />
                    {r.calls_completed} completed
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </>
  );
}

function Header({ onRefresh }) {
  return (
    <div style={{ display: "flex", alignItems: "flex-start" }}>
      <div style={{ flex: 1 }}>
        <h1 className="page-title">Hiring status</h1>
        <p className="page-sub">Computed live from applicant records</p>
      </div>
      <button className="btn-primary" onClick={onRefresh}>
        Refresh
      </button>
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div className="stat">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
    </div>
  );
}