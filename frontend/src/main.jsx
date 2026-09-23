import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  AlertCircle,
  ArrowRight,
  BarChart3,
  CheckCircle2,
  Clock3,
  FileUp,
  GraduationCap,
  RefreshCw,
  Target,
  UploadCloud,
  UserRound,
  UsersRound,
} from "lucide-react";
import "./index.css";

const API_BASE = (
  import.meta.env.VITE_API_URL ||
  import.meta.env.VITE_API_BASE_URL ||
  "/api"
).replace(/\/$/, "");

function apiPath(path) {
  return `${API_BASE}${path}`;
}

function describeDetail(detail) {
  if (Array.isArray(detail)) {
    return detail.join("; ");
  }
  if (detail && typeof detail === "object") {
    if (detail.message && detail.reasons) {
      return `${detail.message}: ${detail.reasons.join(", ")}`;
    }
    return JSON.stringify(detail);
  }
  return detail || "Request failed";
}

async function apiRequest(path, options = {}) {
  const response = await fetch(apiPath(path), options);
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();
  if (!response.ok) {
    throw new Error(describeDetail(payload.detail ?? payload));
  }
  return payload;
}

function formatNumber(value, digits = 3) {
  if (value === null || value === undefined || value === "") return "n/a";
  if (typeof value !== "number") return value;
  return Number.isInteger(value) ? `${value}` : `${Number(value.toFixed(digits))}`;
}

function formatDate(value) {
  if (!value) return "Any time";
  return value;
}

function makeRequestId(employeeId, eventId) {
  const stamp = Date.now().toString(36);
  const random =
    typeof crypto !== "undefined" && crypto.randomUUID
      ? crypto.randomUUID().replaceAll("-", "").slice(0, 10)
      : Math.random().toString(36).slice(2, 12);
  return `ui-${employeeId}-${eventId}-${stamp}-${random}`;
}

function Pill({ children, tone = "slate" }) {
  const tones = {
    slate: "border-slate-200 bg-slate-50 text-slate-700",
    green: "border-emerald-200 bg-emerald-50 text-emerald-800",
    blue: "border-sky-200 bg-sky-50 text-sky-800",
    amber: "border-amber-200 bg-amber-50 text-amber-800",
    red: "border-rose-200 bg-rose-50 text-rose-800",
  };
  return (
    <span className={`inline-flex items-center rounded-md border px-2 py-1 text-xs font-medium ${tones[tone]}`}>
      {children}
    </span>
  );
}

function EmptyState({ icon: Icon = AlertCircle, title, body }) {
  return (
    <div className="empty-state">
      <Icon className="h-5 w-5 text-slate-400" aria-hidden="true" />
      <div>
        <p className="font-semibold text-slate-800">{title}</p>
        {body ? <p className="mt-1 text-sm text-slate-500">{body}</p> : null}
      </div>
    </div>
  );
}

function Stat({ label, value, detail }) {
  return (
    <div className="stat-cell">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-slate-950">{value}</p>
      {detail ? <p className="mt-1 text-xs text-slate-500">{detail}</p> : null}
    </div>
  );
}

function App() {
  const [view, setView] = useState("employee");
  const [employees, setEmployees] = useState([]);
  const [employeeQuery, setEmployeeQuery] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [employeeDetail, setEmployeeDetail] = useState(null);
  const [recommendations, setRecommendations] = useState([]);
  const [hrOverview, setHrOverview] = useState(null);
  const [sessionCompletions, setSessionCompletions] = useState({});
  const [loadingEmployee, setLoadingEmployee] = useState(false);
  const [loadingHr, setLoadingHr] = useState(false);
  const [completingEvent, setCompletingEvent] = useState("");
  const [error, setError] = useState("");
  const [uploadResult, setUploadResult] = useState(null);

  async function loadEmployees(preferredId) {
    const rows = await apiRequest("/employees");
    setEmployees(rows);
    setSelectedId((current) => {
      if (preferredId && rows.some((row) => row.id === preferredId)) return preferredId;
      if (current && rows.some((row) => row.id === current)) return current;
      return rows.find((row) => row.id === "E0002")?.id || rows[0]?.id || "";
    });
    return rows;
  }

  async function loadHrOverview() {
    setLoadingHr(true);
    try {
      setHrOverview(await apiRequest("/hr/overview"));
    } finally {
      setLoadingHr(false);
    }
  }

  async function loadEmployee(employeeId) {
    if (!employeeId) return;
    setLoadingEmployee(true);
    setError("");
    try {
      const [detail, recs] = await Promise.all([
        apiRequest(`/employees/${encodeURIComponent(employeeId)}`),
        apiRequest(`/recommend/${encodeURIComponent(employeeId)}`),
      ]);
      setEmployeeDetail(detail);
      setRecommendations(recs.recommendations || []);
    } catch (exc) {
      setEmployeeDetail(null);
      setRecommendations([]);
      setError(exc.message);
    } finally {
      setLoadingEmployee(false);
    }
  }

  useEffect(() => {
    async function bootstrap() {
      try {
        await Promise.all([loadEmployees(), loadHrOverview()]);
      } catch (exc) {
        setError(exc.message);
      }
    }
    bootstrap();
  }, []);

  useEffect(() => {
    loadEmployee(selectedId);
  }, [selectedId]);

  const filteredEmployees = useMemo(() => {
    const query = employeeQuery.trim().toLowerCase();
    if (!query) return employees;
    return employees.filter((employee) =>
      [employee.id, employee.name, employee.role, employee.grade, employee.department]
        .join(" ")
        .toLowerCase()
        .includes(query),
    );
  }, [employees, employeeQuery]);

  async function markComplete(recommendation) {
    if (!selectedId || completingEvent) return;
    setCompletingEvent(recommendation.event_id);
    setError("");
    try {
      const result = await apiRequest("/complete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          employee_id: selectedId,
          event_id: recommendation.event_id,
          request_id: makeRequestId(selectedId, recommendation.event_id),
        }),
      });
      setEmployeeDetail((current) =>
        current
          ? {
              ...current,
              profile: { ...current.profile, skills: result.skills },
              trajectory: result.trajectory,
            }
          : current,
      );
      setSessionCompletions((current) => ({
        ...current,
        [selectedId]: [
          {
            event_id: recommendation.event_id,
            title: recommendation.title,
            record_id: result.record_id,
            skill_changes: result.skill_changes,
          },
          ...(current[selectedId] || []),
        ],
      }));
      const recs = await apiRequest(`/recommend/${encodeURIComponent(selectedId)}`);
      setRecommendations(recs.recommendations || []);
      await loadHrOverview();
    } catch (exc) {
      setError(exc.message);
    } finally {
      setCompletingEvent("");
    }
  }

  async function handleUpload(submission) {
    setError("");
    setUploadResult(null);
    try {
      const options =
        submission.type === "json"
          ? {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: submission.body,
            }
          : {
              method: "POST",
              body: submission.body,
            };
      const result = await apiRequest("/upload", options);
      setUploadResult(result);
      const nextId = result.employee_ids?.[0];
      await Promise.all([loadEmployees(nextId), loadHrOverview()]);
      if (nextId) {
        setView("employee");
        setSelectedId(nextId);
      }
    } catch (exc) {
      setError(exc.message);
      throw exc;
    }
  }

  return (
    <main className="min-h-screen bg-stone-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-5 sm:px-6 lg:flex-row lg:items-center lg:justify-between lg:px-8">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald-700">
              HackAlem AI / Career Quest
            </p>
            <h1 className="mt-1 text-2xl font-semibold text-slate-950">Explainable career next steps</h1>
          </div>
          <nav className="inline-flex w-full rounded-md border border-slate-200 bg-slate-100 p-1 sm:w-auto">
            <button
              className={`nav-button ${view === "employee" ? "nav-button-active" : ""}`}
              onClick={() => setView("employee")}
              type="button"
            >
              <UserRound className="h-4 w-4" aria-hidden="true" />
              Employee
            </button>
            <button
              className={`nav-button ${view === "hr" ? "nav-button-active" : ""}`}
              onClick={() => setView("hr")}
              type="button"
            >
              <BarChart3 className="h-4 w-4" aria-hidden="true" />
              HR overview
            </button>
          </nav>
        </div>
      </header>

      <div className="mx-auto grid max-w-7xl gap-5 px-4 py-5 sm:px-6 lg:grid-cols-[310px_minmax(0,1fr)] lg:px-8">
        <aside className="space-y-5">
          <EmployeePicker
            employees={filteredEmployees}
            query={employeeQuery}
            selectedId={selectedId}
            total={employees.length}
            onQuery={setEmployeeQuery}
            onSelect={setSelectedId}
          />
          <UploadPanel onUpload={handleUpload} result={uploadResult} />
        </aside>

        <section className="min-w-0">
          {error ? (
            <div className="mb-4 flex items-start gap-3 rounded-md border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              <span>{error}</span>
            </div>
          ) : null}

          {view === "employee" ? (
            <EmployeeView
              detail={employeeDetail}
              recommendations={recommendations}
              loading={loadingEmployee}
              completingEvent={completingEvent}
              completions={sessionCompletions[selectedId] || []}
              onComplete={markComplete}
            />
          ) : (
            <HrView overview={hrOverview} loading={loadingHr} />
          )}
        </section>
      </div>
    </main>
  );
}

function EmployeePicker({ employees, query, selectedId, total, onQuery, onSelect }) {
  return (
    <section className="panel">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="panel-title">Employee</h2>
          <p className="text-sm text-slate-500">{total} profiles loaded</p>
        </div>
        <UsersRound className="h-5 w-5 text-slate-400" aria-hidden="true" />
      </div>
      <label className="mt-4 block text-sm font-medium text-slate-700" htmlFor="employee-search">
        Search
      </label>
      <input
        id="employee-search"
        className="input mt-2"
        value={query}
        onChange={(event) => onQuery(event.target.value)}
        placeholder="E0002, role, department"
      />
      <label className="mt-4 block text-sm font-medium text-slate-700" htmlFor="employee-select">
        Profile
      </label>
      <select
        id="employee-select"
        className="input mt-2"
        value={selectedId}
        onChange={(event) => onSelect(event.target.value)}
      >
        {employees.map((employee) => (
          <option key={employee.id} value={employee.id}>
            {employee.id} / {employee.name}
          </option>
        ))}
      </select>
      {employees.length === 0 ? (
        <p className="mt-3 text-sm text-amber-700">No matching employees.</p>
      ) : null}
    </section>
  );
}

function UploadPanel({ onUpload, result }) {
  const [employeesFile, setEmployeesFile] = useState(null);
  const [historyFile, setHistoryFile] = useState(null);
  const [jsonText, setJsonText] = useState("");
  const [uploading, setUploading] = useState(false);
  const [mode, setMode] = useState("files");
  const [localError, setLocalError] = useState("");

  async function submit(event) {
    event.preventDefault();
    setLocalError("");
    setUploading(true);
    try {
      if (mode === "json") {
        const body = jsonText.trim();
        if (!body) throw new Error("Paste a JSON upload batch first.");
        JSON.parse(body);
        await onUpload({ type: "json", body });
      } else {
        if (!employeesFile && !historyFile) throw new Error("Choose at least one upload file.");
        const form = new FormData();
        if (employeesFile) form.append("employees_file", employeesFile);
        if (historyFile) form.append("history_file", historyFile);
        await onUpload({ type: "files", body: form });
      }
    } catch (exc) {
      setLocalError(exc.message);
    } finally {
      setUploading(false);
    }
  }

  return (
    <section className="panel">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="panel-title">Upload</h2>
          <p className="text-sm text-slate-500">Add jury profiles and history</p>
        </div>
        <UploadCloud className="h-5 w-5 text-slate-400" aria-hidden="true" />
      </div>

      <div className="mt-4 grid grid-cols-2 rounded-md border border-slate-200 bg-slate-100 p-1">
        <button
          className={`segmented-button ${mode === "files" ? "segmented-button-active" : ""}`}
          type="button"
          onClick={() => setMode("files")}
        >
          Files
        </button>
        <button
          className={`segmented-button ${mode === "json" ? "segmented-button-active" : ""}`}
          type="button"
          onClick={() => setMode("json")}
        >
          JSON
        </button>
      </div>

      <form className="mt-4 space-y-3" onSubmit={submit}>
        {mode === "files" ? (
          <>
            <label className="file-drop">
              <FileUp className="h-4 w-4 text-slate-500" aria-hidden="true" />
              <span>
                <span className="block text-sm font-medium text-slate-800">employees_file</span>
                <span className="block truncate text-xs text-slate-500">
                  {employeesFile?.name || "JSON wrapper with employees[]"}
                </span>
              </span>
              <input
                className="sr-only"
                type="file"
                accept=".json,application/json"
                onChange={(event) => setEmployeesFile(event.target.files?.[0] || null)}
              />
            </label>
            <label className="file-drop">
              <FileUp className="h-4 w-4 text-slate-500" aria-hidden="true" />
              <span>
                <span className="block text-sm font-medium text-slate-800">history_file</span>
                <span className="block truncate text-xs text-slate-500">
                  {historyFile?.name || "activity_history.csv columns"}
                </span>
              </span>
              <input
                className="sr-only"
                type="file"
                accept=".csv,text/csv"
                onChange={(event) => setHistoryFile(event.target.files?.[0] || null)}
              />
            </label>
          </>
        ) : (
          <textarea
            className="input min-h-44 resize-y font-mono text-xs"
            value={jsonText}
            onChange={(event) => setJsonText(event.target.value)}
            placeholder='{"employees":[...],"activity_history":[...]}'
          />
        )}

        {localError ? <p className="text-sm text-rose-700">{localError}</p> : null}
        {result ? (
          <div className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
            Inserted {result.inserted.employees} employee(s), {result.inserted.activity_history} history row(s).
            {result.employee_ids.length ? ` Opened ${result.employee_ids[0]}.` : ""}
          </div>
        ) : null}
        <button className="primary-button w-full" type="submit" disabled={uploading}>
          {uploading ? <RefreshCw className="h-4 w-4 animate-spin" /> : <UploadCloud className="h-4 w-4" />}
          Upload and open
        </button>
      </form>
    </section>
  );
}

function EmployeeView({ detail, recommendations, loading, completingEvent, completions, onComplete }) {
  if (loading && !detail) {
    return <Skeleton title="Loading employee profile" />;
  }
  if (!detail) {
    return <EmptyState title="No employee selected" body="Choose a profile from the selector." />;
  }

  const { profile, trajectory } = detail;

  return (
    <div className="space-y-5">
      <section className="panel">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-2xl font-semibold text-slate-950">{profile.full_name}</h2>
              <Pill tone="blue">{profile.employee_id}</Pill>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              <Pill>{profile.department}</Pill>
              <Pill>{profile.role}</Pill>
              <Pill tone="green">{profile.grade}</Pill>
              <Pill tone="amber">{profile.work_format}</Pill>
            </div>
          </div>
          <div className="min-w-56 rounded-md border border-emerald-200 bg-emerald-50 p-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-emerald-800">Target trajectory</p>
            <p className="mt-1 font-semibold text-emerald-950">
              {trajectory.target_role} / {trajectory.target_grade}
            </p>
            <div className="mt-3 h-2 rounded-full bg-emerald-100">
              <div className="h-2 rounded-full bg-emerald-600" style={{ width: `${trajectory.progress_pct}%` }} />
            </div>
            <p className="mt-2 text-sm text-emerald-900">{formatNumber(trajectory.progress_pct, 2)}% of target levels met</p>
          </div>
        </div>
        <div className="mt-5 grid gap-3 sm:grid-cols-3">
          <Stat label="Total skill gap" value={formatNumber(trajectory.total_gap)} detail="levels missing" />
          <Stat label="Critical gap" value={formatNumber(trajectory.critical_gap)} detail="critical levels missing" />
          <Stat label="Last review" value={profile.last_review_date} detail={`${profile.tenure_months} months tenure`} />
        </div>
      </section>

      <section className="panel">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="panel-title">Current Skills vs Target Grade</h2>
            <p className="text-sm text-slate-500">Assessed levels compared with target requirements</p>
          </div>
          <Target className="h-5 w-5 text-slate-400" aria-hidden="true" />
        </div>
        <SkillTable skills={trajectory.skills} />
      </section>

      <section className="panel">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="panel-title">Completed Activities</h2>
            <p className="text-sm text-slate-500">Completions made from this screen</p>
          </div>
          <CheckCircle2 className="h-5 w-5 text-slate-400" aria-hidden="true" />
        </div>
        {completions.length ? (
          <div className="mt-4 space-y-3">
            {completions.map((item) => (
              <div key={item.record_id} className="completion-row">
                <div>
                  <p className="font-medium text-slate-900">{item.title}</p>
                  <p className="mt-1 text-xs text-slate-500">
                    {item.event_id} / record {item.record_id}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {item.skill_changes.map((change) => (
                    <Pill key={change.skill_id} tone={change.gain > 0 ? "green" : "slate"}>
                      {change.skill_id}: {formatNumber(change.before)} to {formatNumber(change.after)}
                    </Pill>
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState title="No completion posted in this UI session" body="Historical employee activity is kept out of the profile endpoint." />
        )}
      </section>

      <section className="space-y-3">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 className="text-xl font-semibold text-slate-950">Recommended Next Steps</h2>
            <p className="text-sm text-slate-500">Each card exposes the deterministic “why” values used for ranking</p>
          </div>
          <Pill tone={recommendations.length ? "green" : "amber"}>{recommendations.length} step(s)</Pill>
        </div>
        {recommendations.length ? (
          <div className="space-y-4">
            {recommendations.map((recommendation, index) => (
              <RecommendationCard
                key={recommendation.event_id}
                recommendation={recommendation}
                rank={index + 1}
                completing={completingEvent === recommendation.event_id}
                disabled={Boolean(completingEvent)}
                onComplete={() => onComplete(recommendation)}
              />
            ))}
          </div>
        ) : (
          <EmptyState
            icon={GraduationCap}
            title="No eligible useful step"
            body="The engine returned zero positive-score recommendations for this profile."
          />
        )}
      </section>
    </div>
  );
}

function SkillTable({ skills }) {
  return (
    <div className="mt-4 overflow-x-auto">
      <table className="data-table">
        <thead>
          <tr>
            <th>Skill</th>
            <th>Current to required</th>
            <th>Gap</th>
            <th>Critical</th>
          </tr>
        </thead>
        <tbody>
          {skills.map((skill) => {
            const ratio = skill.required ? Math.min(100, (skill.current / skill.required) * 100) : 100;
            return (
              <tr key={skill.skill_id}>
                <td>
                  <p className="font-medium text-slate-900">{skill.skill_name}</p>
                  <p className="text-xs text-slate-500">{skill.skill_id}</p>
                </td>
                <td className="min-w-52">
                  <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                    {formatNumber(skill.current)}
                    <ArrowRight className="h-3.5 w-3.5 text-slate-400" aria-hidden="true" />
                    {formatNumber(skill.required)}
                  </div>
                  <div className="mt-2 h-2 rounded-full bg-slate-100">
                    <div
                      className={`h-2 rounded-full ${skill.gap > 0 ? "bg-sky-600" : "bg-emerald-600"}`}
                      style={{ width: `${ratio}%` }}
                    />
                  </div>
                </td>
                <td>
                  <Pill tone={skill.gap > 0 ? "amber" : "green"}>{formatNumber(skill.gap)}</Pill>
                </td>
                <td>
                  <Pill tone={skill.critical ? "red" : "slate"}>{skill.critical ? "critical" : "supporting"}</Pill>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function RecommendationCard({ recommendation, rank, completing, disabled, onComplete }) {
  const factors = recommendation.factors;
  const engagement = factors.engagement;
  return (
    <article className="recommendation-card">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <Pill tone="blue">#{rank}</Pill>
            <Pill>{recommendation.event_id}</Pill>
            <Pill tone="green">score {formatNumber(recommendation.score)}</Pill>
          </div>
          <h3 className="mt-3 text-xl font-semibold text-slate-950">{recommendation.title}</h3>
          <div className="mt-3 flex flex-wrap gap-2">
            <Pill>{recommendation.type}</Pill>
            <Pill>{recommendation.format}</Pill>
            <Pill tone="amber">{formatNumber(recommendation.duration_hours)}h</Pill>
            <Pill tone="blue">
              <Clock3 className="mr-1 h-3 w-3" aria-hidden="true" />
              {formatDate(recommendation.upcoming_sessions?.[0])}
            </Pill>
          </div>
        </div>
        <button className="primary-button" type="button" onClick={onComplete} disabled={disabled}>
          {completing ? <RefreshCw className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
          Mark complete
        </button>
      </div>

      <div className="mt-5 grid gap-3 lg:grid-cols-[minmax(0,1fr)_280px]">
        <div className="space-y-3">
          <div>
            <h4 className="evidence-title">Skill gaps used</h4>
            <div className="mt-2 grid gap-2 sm:grid-cols-2">
              {factors.gaps.map((gap) => (
                <div key={gap.skill_id} className="evidence-row">
                  <div>
                    <p className="font-medium text-slate-900">{gap.skill_name}</p>
                    <p className="text-xs text-slate-500">{gap.skill_id}</p>
                  </div>
                  <div className="text-right">
                    <p className="font-semibold text-slate-950">
                      {formatNumber(gap.current)} to {formatNumber(gap.required)}
                    </p>
                    <p className="text-xs text-slate-500">
                      gap {formatNumber(gap.gap)} / gain {formatNumber(gap.effective_gain)}
                    </p>
                    {gap.critical ? <Pill tone="red">critical</Pill> : null}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div>
            <h4 className="evidence-title">Rationale</h4>
            <p className="mt-2 rounded-md border border-slate-200 bg-white px-3 py-3 text-sm leading-6 text-slate-700">
              {recommendation.rationale}
            </p>
            <p className="mt-2 text-xs text-slate-500">
              Explanation source: {recommendation.explanation.source}
              {recommendation.explanation.fallback_reason ? ` / ${recommendation.explanation.fallback_reason}` : ""}
            </p>
          </div>
        </div>

        <div className="space-y-3">
          <div className="metric-panel">
            <h4 className="evidence-title">Engagement signal</h4>
            <dl className="mt-3 grid grid-cols-2 gap-2 text-sm">
              <Metric label="Type" value={engagement.type} />
              <Metric label="Skipped" value={formatNumber(engagement.skip_count)} />
              <Metric label="Self-completed" value={formatNumber(engagement.self_completion_count)} />
              <Metric label="Self factor" value={formatNumber(engagement.self_factor)} />
              <Metric label="Multiplier" value={formatNumber(engagement.multiplier)} tone="strong" />
              <Metric label="Benefit" value={formatNumber(factors.benefit)} tone="strong" />
            </dl>
          </div>
          <GatewayList gateways={recommendation.gateway_to || []} />
        </div>
      </div>
    </article>
  );
}

function Metric({ label, value, tone }) {
  return (
    <div className={tone === "strong" ? "metric-cell-strong" : "metric-cell"}>
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className="mt-1 break-words font-semibold text-slate-950">{value}</dd>
    </div>
  );
}

function GatewayList({ gateways }) {
  return (
    <div className="metric-panel">
      <h4 className="evidence-title">Gateway unlocks</h4>
      {gateways.length ? (
        <div className="mt-3 space-y-3">
          {gateways.map((gateway) => (
            <div key={gateway.event_id} className="rounded-md border border-sky-200 bg-sky-50 px-3 py-2">
              <p className="font-medium text-sky-950">
                {gateway.event_id}: {gateway.title}
              </p>
              <p className="mt-1 text-xs text-sky-800">
                {gateway.unlocked_after_completion ? "Unlocked after completion" : "Progress toward prerequisites"}
              </p>
              <div className="mt-2 space-y-1">
                {gateway.blocking_prerequisites.map((blocker) => (
                  <p key={blocker.skill_id} className="text-xs text-sky-900">
                    {blocker.skill_name}: {formatNumber(blocker.current)} to {formatNumber(blocker.after_completion)} /
                    requires {formatNumber(blocker.required)}
                  </p>
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="mt-3 text-sm text-slate-500">No locked follow-up event is opened by this step.</p>
      )}
    </div>
  );
}

function HrView({ overview, loading }) {
  if (loading && !overview) {
    return <Skeleton title="Loading HR aggregates" />;
  }
  if (!overview) {
    return <EmptyState title="No HR overview loaded" body="The aggregate endpoint did not return data yet." />;
  }

  const lagging = overview.most_lagging_skills.slice(0, 10);
  const participation = [...overview.participation_by_activity]
    .sort((a, b) => b.records - a.records || a.event_id.localeCompare(b.event_id))
    .slice(0, 12);
  const maxGap = Math.max(...lagging.map((skill) => skill.total_gap), 1);

  return (
    <div className="space-y-5">
      <section className="panel">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <h2 className="text-2xl font-semibold text-slate-950">HR Overview</h2>
            <p className="mt-1 text-sm text-slate-500">
              Aggregate gaps and participation only / no employee engagement history exposed
            </p>
          </div>
          <Pill tone="blue">Snapshot {overview.as_of_date}</Pill>
        </div>
        <div className="mt-5 grid gap-3 sm:grid-cols-3">
          <Stat label="Employees" value={overview.employee_count} detail="profiles in scope" />
          <Stat
            label="No recommended step"
            value={overview.employees_without_recommendation.count}
            detail="empty positive recommendation list"
          />
          <Stat label="Lagging skills" value={overview.most_lagging_skills.length} detail="skills with a target gap" />
        </div>
      </section>

      <section className="panel">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="panel-title">Most-Frequently Lagging Skills</h2>
            <p className="text-sm text-slate-500">Sorted by total missing levels across employees</p>
          </div>
          <Target className="h-5 w-5 text-slate-400" aria-hidden="true" />
        </div>
        <div className="mt-4 space-y-3">
          {lagging.map((skill) => (
            <div key={skill.skill_id} className="hr-row">
              <div className="min-w-0">
                <p className="font-medium text-slate-900">{skill.skill_name}</p>
                <p className="text-xs text-slate-500">{skill.skill_id}</p>
              </div>
              <div className="min-w-0 flex-1">
                <div className="h-2 rounded-full bg-slate-100">
                  <div
                    className="h-2 rounded-full bg-sky-600"
                    style={{ width: `${Math.max(5, (skill.total_gap / maxGap) * 100)}%` }}
                  />
                </div>
              </div>
              <div className="flex flex-wrap justify-end gap-2 text-right">
                <Pill tone="amber">{skill.total_gap} total gap</Pill>
                <Pill>{skill.employees_affected} people</Pill>
                <Pill tone={skill.critical_employees ? "red" : "slate"}>{skill.critical_employees} critical</Pill>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="panel">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="panel-title">Participation by Activity</h2>
            <p className="text-sm text-slate-500">Top activity records with status totals</p>
          </div>
          <BarChart3 className="h-5 w-5 text-slate-400" aria-hidden="true" />
        </div>
        <div className="mt-4 overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th>Activity</th>
                <th>Type</th>
                <th>Records</th>
                <th>Participants</th>
                <th>Status counts</th>
              </tr>
            </thead>
            <tbody>
              {participation.map((activity) => (
                <tr key={activity.event_id}>
                  <td>
                    <p className="font-medium text-slate-900">{activity.title}</p>
                    <p className="text-xs text-slate-500">{activity.event_id}</p>
                  </td>
                  <td>{activity.type}</td>
                  <td>{activity.records}</td>
                  <td>{activity.participants}</td>
                  <td>
                    <div className="flex flex-wrap gap-1.5">
                      {Object.entries(activity.status_counts).map(([status, count]) => (
                        <Pill key={status}>{status}: {count}</Pill>
                      ))}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function Skeleton({ title }) {
  return (
    <section className="panel">
      <div className="flex items-center gap-3">
        <RefreshCw className="h-5 w-5 animate-spin text-slate-400" aria-hidden="true" />
        <p className="font-semibold text-slate-800">{title}</p>
      </div>
      <div className="mt-5 space-y-3">
        <div className="h-4 w-2/3 rounded bg-slate-100" />
        <div className="h-4 w-1/2 rounded bg-slate-100" />
        <div className="h-24 rounded bg-slate-100" />
      </div>
    </section>
  );
}

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
