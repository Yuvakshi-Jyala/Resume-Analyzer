import { useState } from "react";
import Dashboard from "./pages/Dashboard.jsx";
import Analyzer from "./pages/Analyzer.jsx";

export default function App() {
  const [page, setPage] = useState("dashboard");
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className="app">
      <aside className={`sidebar ${collapsed ? "collapsed" : ""}`}>
        <div className="brand">
          {!collapsed && (
            <div className="brand-name">
              <i className="ti ti-briefcase" aria-hidden="true" />
              <span>CogitX</span>
            </div>
          )}
          <button
            className="collapse-btn"
            onClick={() => setCollapsed((v) => !v)}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            title={collapsed ? "Expand" : "Collapse"}
          >
            <i className="ti ti-layout-sidebar-left-collapse" aria-hidden="true" />
          </button>
        </div>

        <button
          className={`nav-item ${page === "dashboard" ? "active" : ""}`}
          onClick={() => setPage("dashboard")}
          title="Dashboard"
        >
          <i className="ti ti-chart-bar" aria-hidden="true" />
          {!collapsed && <span>Dashboard</span>}
        </button>
        <button
          className={`nav-item ${page === "analyzer" ? "active" : ""}`}
          onClick={() => setPage("analyzer")}
          title="Resume analyzer"
        >
          <i className="ti ti-file-search" aria-hidden="true" />
          {!collapsed && <span>Resume analyzer</span>}
        </button>

        <div className="sidebar-footer">
          <div className="avatar">Y</div>
          {!collapsed && <span>Admin</span>}
        </div>
      </aside>

      <main className="main">
        {page === "dashboard" ? <Dashboard /> : <Analyzer />}
      </main>
    </div>
  );
}
