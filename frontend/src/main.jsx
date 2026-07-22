import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import "./styles.css";

const columns = [
  {
    accessorKey: "ticker",
    header: "Ticker",
    cell: ({ row }) => <strong className="ticker-cell">{row.original.ticker}</strong>,
  },
  {
    accessorKey: "company_name",
    header: "Issuer",
    cell: ({ row }) => (
      <div>
        <strong>{row.original.company_name}</strong>
        <span className="muted">CIK {row.original.cik}</span>
      </div>
    ),
  },
  {
    accessorKey: "value",
    header: "Revenue",
    cell: ({ row }) => <strong>{formatCurrency(row.original.value)}</strong>,
  },
  {
    accessorKey: "fiscal_year",
    header: "Period",
    cell: ({ row }) => `${row.original.fiscal_year} ${row.original.fiscal_quarter === 4 ? "FY" : `Q${row.original.fiscal_quarter}`}`,
  },
  {
    accessorKey: "quality_state",
    header: "Quality",
    cell: ({ row }) => <QualityPill value={row.original.quality_state} />,
  },
  {
    accessorKey: "filed_at",
    header: "Filed",
    cell: ({ row }) => formatDate(row.original.filed_at),
  },
];

function formatCurrency(value) {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return value ?? "n/a";
  return new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: 1,
    style: "currency",
    currency: "USD",
  }).format(amount);
}

function formatDate(value) {
  if (!value) return "n/a";
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" }).format(new Date(value));
}

function QualityPill({ value }) {
  return <span className={`quality-pill ${value === "verified" ? "is-good" : ""}`}>{value ?? "unknown"}</span>;
}

function App() {
  const [rows, setRows] = useState([]);
  const [history, setHistory] = useState([]);
  const [universes, setUniverses] = useState([]);
  const [status, setStatus] = useState("Loading filing-backed data");
  const [busy, setBusy] = useState(false);
  const [globalFilter, setGlobalFilter] = useState("");
  const [sorting, setSorting] = useState([]);

  async function loadData() {
    const [dashboardResponse, historyResponse, universeResponse] = await Promise.all([
      fetch("/api/v1/dashboard?ticker=AAPL"),
      fetch("/api/v1/companies/AAPL/history"),
      fetch("/api/v1/universes"),
    ]);
    if (!dashboardResponse.ok || !historyResponse.ok || !universeResponse.ok) {
      throw new Error("The local API is not ready");
    }
    setRows(await dashboardResponse.json());
    setHistory(await historyResponse.json());
    setUniverses(await universeResponse.json());
    setStatus("Synced from SEC filing data");
  }

  useEffect(() => {
    loadData().catch((error) => setStatus(error.message));
  }, []);

  async function refreshAapl() {
    setBusy(true);
    setStatus("Fetching the latest Apple filing from SEC");
    try {
      const response = await fetch("/api/v1/refresh/AAPL", { method: "POST" });
      if (!response.ok) throw new Error("SEC refresh failed");
      await loadData();
    } catch (error) {
      setStatus(error.message);
    } finally {
      setBusy(false);
    }
  }

  const latest = rows[0];
  const table = useReactTable({
    data: rows,
    columns,
    state: { globalFilter, sorting },
    onGlobalFilterChange: setGlobalFilter,
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });
  const chartData = history.map((point) => ({
    period: point.fiscal_quarter === 4 ? `${point.fiscal_year} FY` : `${point.fiscal_year} Q${point.fiscal_quarter}`,
    revenue: Number(point.value),
  }));
  const holdingCount = universes.reduce((total, universe) => total + Number(universe.member_count || 0), 0);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-mark"><span>FA</span><div><strong>Financial</strong><small>Acceleration Tracker</small></div></div>
        <div className="sidebar-label">Workspace</div>
        <nav className="nav-list" aria-label="Primary navigation">
          <a className="nav-item active" href="#overview"><span className="nav-icon">◈</span>Overview</a>
          <a className="nav-item" href="#history"><span className="nav-icon">∿</span>Company history</a>
          <a className="nav-item" href="#metrics"><span className="nav-icon">ƒ</span>Defined metrics</a>
        </nav>
        <div className="sidebar-footnote"><span className="live-dot" />Local filing workspace</div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div><span className="eyebrow">Research workspace / MVP</span><h1>Overview</h1></div>
          <button className="refresh-button" onClick={refreshAapl} disabled={busy}>{busy ? "Refreshing..." : "Refresh AAPL"}</button>
        </header>

        <div className="status-line"><span className="status-dot" />{status}<span className="status-rule" />SEC identity configured</div>

        <section id="overview" className="hero-grid">
          <article className="hero-card">
            <div className="card-kicker">Tracked issuer</div>
            <div className="hero-title-row"><div><h2>{latest?.ticker || "AAPL"}</h2><p>{latest?.company_name || "Apple Inc."}</p></div><span className="source-badge">10-K / 10-Q</span></div>
            <div className="hero-value">{latest ? formatCurrency(latest.value) : "—"}</div>
            <div className="hero-meta">Revenue · {latest ? `${latest.fiscal_year} ${latest.fiscal_quarter === 4 ? "FY" : `Q${latest.fiscal_quarter}`}` : "awaiting first refresh"}</div>
          </article>
          <StatCard label="Portfolio coverage" value={`${holdingCount || "—"}`} detail="issuer in local portfolio" />
          <StatCard label="Data posture" value="Filing-backed" detail="not real-time prices or P&L" />
        </section>

        <section className="content-grid">
          <article className="panel table-panel">
            <div className="panel-heading"><div><span className="eyebrow">Collection</span><h2>Tracked companies</h2></div><div className="table-tools"><input aria-label="Filter companies" placeholder="Filter" value={globalFilter} onChange={(event) => setGlobalFilter(event.target.value)} /><span className="count-badge">{table.getFilteredRowModel().rows.length} issuer</span></div></div>
            <div className="table-wrap"><table><thead>{table.getHeaderGroups().map((headerGroup) => <tr key={headerGroup.id}>{headerGroup.headers.map((header) => <th key={header.id}>{header.isPlaceholder ? null : <button className="sort-button" onClick={header.column.getToggleSortingHandler()}>{flexRender(header.column.columnDef.header, header.getContext())}<span>{header.column.getIsSorted() === "asc" ? " ↑" : header.column.getIsSorted() === "desc" ? " ↓" : " ↕"}</span></button>}</th>)}</tr>)}</thead><tbody>{table.getRowModel().rows.map((row) => <tr key={row.id}>{row.getVisibleCells().map((cell) => <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>)}</tr>)}</tbody></table>{rows.length === 0 && <EmptyState />}{rows.length > 0 && table.getRowModel().rows.length === 0 && <EmptyState message="No companies match this filter" />}</div>
          </article>

          <article id="history" className="panel chart-panel">
            <div className="panel-heading"><div><span className="eyebrow">Selected metric</span><h2>Revenue history</h2></div><span className="metric-tag">USD</span></div>
            <div className="chart-wrap">{chartData.length ? <ResponsiveContainer width="100%" height="100%"><LineChart data={chartData} margin={{ top: 10, right: 8, left: -18, bottom: 0 }}><CartesianGrid stroke="#e6ebf2" strokeDasharray="3 3" vertical={false} /><XAxis dataKey="period" axisLine={false} tickLine={false} tick={{ fill: "#8490a3", fontSize: 11 }} /><YAxis axisLine={false} tickLine={false} tick={{ fill: "#8490a3", fontSize: 11 }} tickFormatter={(value) => `$${Math.round(value / 1000000)}M`} /><Tooltip formatter={(value) => formatCurrency(value)} contentStyle={{ border: "1px solid #e6ebf2", borderRadius: 8, boxShadow: "0 8px 24px rgba(16,26,43,.08)" }} /><Line type="monotone" dataKey="revenue" stroke="#e68a42" strokeWidth={3} dot={{ r: 4, fill: "#e68a42", strokeWidth: 2, stroke: "#fff" }} activeDot={{ r: 6 }} /></LineChart></ResponsiveContainer> : <EmptyState message="Refresh AAPL to populate history" />}</div>
            <div className="history-list">{history.slice(-4).reverse().map((point) => <a className="history-item" href={point.source_url} target="_blank" rel="noreferrer" key={point.accession}><span><strong>{point.fiscal_quarter === 4 ? `${point.fiscal_year} FY` : `${point.fiscal_year} Q${point.fiscal_quarter}`}</strong><small>{point.form_type} · {point.accession}</small></span><span><strong>{formatCurrency(point.value)}</strong><QualityPill value={point.quality_state} /></span></a>)}</div>
            <div className="chart-footnote">Quarter-aligned reported revenue with accession, form, quality, and source link retained.</div>
          </article>
        </section>

        <section id="metrics" className="bottom-callout"><div><span className="eyebrow">Extensible metric registry</span><h2>Define the next metric without changing the dashboard shell.</h2><p>Use the metric-definition API to dry-run and activate declarative, provenance-aware calculations.</p></div><span className="api-chip">POST /api/v1/metric-definitions/dry-run</span></section>
        {latest && <footer className="provenance-footer">Source: <a href={latest.source_url} target="_blank" rel="noreferrer">SEC filing {latest.accession}</a> · Filed {formatDate(latest.filed_at)} · Quality <QualityPill value={latest.quality_state} /></footer>}
      </main>
    </div>
  );
}

function StatCard({ label, value, detail }) {
  return <article className="stat-card"><span className="card-kicker">{label}</span><strong>{value}</strong><span>{detail}</span></article>;
}

function EmptyState({ message = "No filing-backed observations yet" }) {
  return <div className="empty-state">{message}</div>;
}

createRoot(document.getElementById("root")).render(<React.StrictMode><App /></React.StrictMode>);
