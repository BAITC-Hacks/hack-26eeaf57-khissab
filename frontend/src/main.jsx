import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  AlertCircle, ArrowRight, ArrowUpRight, Check, ChevronRight, Eye, EyeOff,
  History, Layers3, LayoutDashboard, LockKeyhole, LogOut, RefreshCw,
  Route, ShieldCheck, Sparkles, UploadCloud, UsersRound,
} from "lucide-react";
import {
  Brand, EmployeePicker, EmployeeView, HrView, initials,
  Skeleton, UploadPanel,
} from "./ui.jsx";
import "./index.css";
import { loadEmployeeResources } from "./loadEmployee.js";
import { createApiRequest } from "./api.js";

const API_BASE = (
  import.meta.env.VITE_API_URL ||
  import.meta.env.VITE_API_BASE_URL ||
  "/api"
).replace(/\/$/, "");

const apiRequest = createApiRequest(API_BASE);

function makeRequestId(employeeId, eventId) {
  const stamp = Date.now().toString(36);
  const random =
    typeof crypto !== "undefined" && crypto.randomUUID
      ? crypto.randomUUID().replaceAll("-", "").slice(0, 10)
      : Math.random().toString(36).slice(2, 12);
  return `ui-${employeeId}-${eventId}-${stamp}-${random}`;
}

function SessionApp() {
  const [user, setUser] = useState(null);
  const [checking, setChecking] = useState(Boolean(sessionStorage.getItem("career-quest-session")));
  useEffect(() => {
    let active = true;
    const initialToken = sessionStorage.getItem("career-quest-session");
    const controller = new AbortController();
    function clear() { sessionStorage.removeItem("career-quest-session"); setUser(null); setChecking(false); }
    window.addEventListener("session-expired", clear);
    const isCurrent = () => active && sessionStorage.getItem("career-quest-session") === initialToken;
    if (initialToken) {
      apiRequest("/auth/me", { signal: controller.signal })
        .then((identity) => { if (isCurrent()) setUser(identity); })
        .catch(() => { if (isCurrent()) clear(); })
        .finally(() => { if (active) setChecking(false); });
    }
    return () => { active = false; controller.abort(); window.removeEventListener("session-expired", clear); };
  }, []);
  async function signOut() {
    try { await apiRequest("/auth/logout", { method: "POST" }); }
    finally { sessionStorage.removeItem("career-quest-session"); setUser(null); }
  }
  if (checking) return <main className="session-loading"><Brand /><Skeleton title="Checking your session" /></main>;
  if (!user) return <LoginView onLogin={(result) => {
    sessionStorage.setItem("career-quest-session", result.access_token);
    setUser(result.user);
  }} />;
  return <App key={user.username} user={user} onSignOut={signOut} />;
}

function LoginView({ onLogin }) {
  const [username, setUsername] = useState("");
  const [code, setCode] = useState("");
  const [showCode, setShowCode] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [demo, setDemo] = useState({ loading: true, enabled: false });
  const [demoAttempt, setDemoAttempt] = useState(0);
  const [showAccount, setShowAccount] = useState(false);
  const signingIn = useRef(false);
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 4000);
    setDemo({ loading: true, enabled: false });
    apiRequest("/auth/demo", { signal: controller.signal })
      .then((options) => { if (active) setDemo({ ...options, loading: false }); })
      .catch(() => { if (active) setDemo({ loading: false, enabled: false, failed: true }); })
      .finally(() => clearTimeout(timeout));
    return () => { active = false; clearTimeout(timeout); controller.abort(); };
  }, [demoAttempt]);

  async function signIn(path, body, action) {
    if (signingIn.current) return;
    signingIn.current = true;
    setBusy(action); setError("");
    try {
      onLogin(await apiRequest(path, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }));
    } catch (exc) { setError(exc.message); }
    finally { signingIn.current = false; setBusy(""); }
  }
  async function submit(event) {
    event.preventDefault();
    await signIn("/auth/login", { username: username.trim(), access_code: code.trim() }, "account");
  }
  return <main className="login-page">
    <section className="login-story" aria-label="Welcome to Career Quest">
      <Brand light />
      <div className="login-story-content"><span className="login-kicker"><span /> MADE FOR YOUR NEXT CHAPTER</span><h1>Great careers <br />grow one<br /><em>step at a time.</em></h1><p>Your ambition deserves a direction. Turn your skills, goals and curiosity into a path that feels like you.</p>
        <div className="journey-illustration" aria-hidden="true"><div className="journey-line" /><div className="journey-stop stop-one"><span><Check size={17} /></span><p>Where you are</p></div><div className="journey-stop stop-two"><span><Sparkles size={19} /></span><p>Your next step</p></div><div className="journey-stop stop-three"><span><ArrowUpRight size={22} /></span><p>What’s possible</p></div></div>
      </div>
      <div className="login-story-footer"><span>HackAlem AI</span><span>Halyk Bank track <ArrowUpRight size={14} aria-hidden="true" /></span></div>
    </section>
    <section className="login-form-side"><div className="login-top-note"><ShieldCheck size={16} aria-hidden="true" />Your personal development workspace</div><div className="login-form-wrap"><span className="welcome-icon"><Route size={27} aria-hidden="true" /></span><p className="eyebrow">{demo.enabled ? "HACKATHON DEMO" : "GOOD TO HAVE YOU HERE"}</p><h2>{demo.enabled ? "Choose your workspace." : <>Your next chapter <br />starts here.</>}</h2><p className="login-description">{demo.enabled ? "Explore Career Quest in one click. No account setup needed." : "Sign in to discover what’s next for you."}</p>
      {demo.loading && <p className="demo-loading" role="status">Checking demo access…</p>}
      {demo.failed && <div className="demo-unavailable"><p>Could not check demo access. Retry or use your account below.</p><button type="button" className="secondary-button" disabled={Boolean(busy)} onClick={() => setDemoAttempt((attempt) => attempt + 1)}>Retry demo access</button></div>}
      {demo.enabled && <div className="demo-accounts" aria-label="Demo workspaces">
        <button type="button" className="demo-account" aria-label="Try employee view" disabled={Boolean(busy) || !demo.employee_id} onClick={() => signIn("/auth/demo/login", { account: "employee" }, "employee")}>
          <span className="demo-account-icon"><Route size={22} aria-hidden="true" /></span><span className="demo-account-copy"><strong>{busy === "employee" ? "Opening employee view…" : "Try employee view"}</strong><span>{demo.employee_id ? "Skills, recommendations & progress" : "Sample employee is unavailable"}</span></span>{busy === "employee" ? <RefreshCw size={18} className="animate-spin" aria-hidden="true" /> : <ArrowRight size={18} aria-hidden="true" />}
        </button>
        <button type="button" className="demo-account" aria-label="Try HR workspace" disabled={Boolean(busy)} onClick={() => signIn("/auth/demo/login", { account: "hr" }, "hr")}>
          <span className="demo-account-icon"><UsersRound size={22} aria-hidden="true" /></span><span className="demo-account-copy"><strong>{busy === "hr" ? "Opening HR workspace…" : "Try HR workspace"}</strong><span>Team insights & profile uploads</span></span>{busy === "hr" ? <RefreshCw size={18} className="animate-spin" aria-hidden="true" /> : <ArrowRight size={18} aria-hidden="true" />}
        </button>
        <p className="demo-switch-hint">Sign out anytime to try the other workspace.</p>
      </div>}
      {error && <p role="alert" className="notice notice-error login-error"><AlertCircle size={17} aria-hidden="true" />{error}</p>}
      {demo.enabled && <button type="button" className="account-toggle" aria-expanded={showAccount} aria-controls="account-login" disabled={Boolean(busy)} onClick={() => { setShowAccount(!showAccount); setError(""); }}>{showAccount ? "Hide account sign-in" : "Use my own account"}<ChevronRight size={16} aria-hidden="true" /></button>}
      <form id="account-login" onSubmit={submit} className="login-form" hidden={demo.loading || (demo.enabled && !showAccount)}>
        <div><label htmlFor="username" className="field-label">Employee ID or HR account</label><input id="username" autoComplete="username" autoCapitalize="none" spellCheck={false} required disabled={Boolean(busy)} className="input" value={username} onChange={(e) => setUsername(e.target.value)} placeholder="E0002 or hr" aria-describedby="account-hint" /><p id="account-hint" className="field-hint">Enter your employee ID, or hr for the HR workspace.</p></div>
        <div><label htmlFor="access-code" className="field-label">Access code</label><div className="password-input"><input id="access-code" type={showCode ? "text" : "password"} autoComplete="current-password" autoCapitalize="none" spellCheck={false} required disabled={Boolean(busy)} className="input" value={code} onChange={(e) => setCode(e.target.value)} placeholder="Enter your access code" /><button type="button" className="icon-button" disabled={Boolean(busy)} onClick={() => setShowCode(!showCode)} aria-label={showCode ? "Hide access code" : "Show access code"} aria-pressed={showCode}>{showCode ? <EyeOff size={18} aria-hidden="true" /> : <Eye size={18} aria-hidden="true" />}</button></div></div>
        <button type="submit" className="primary-button login-submit" disabled={Boolean(busy)}>{busy === "account" ? <RefreshCw size={18} className="animate-spin" aria-hidden="true" /> : null}{busy === "account" ? "Signing in…" : "Sign in"}<ArrowRight size={18} aria-hidden="true" /></button>
      </form><div className="login-privacy"><LockKeyhole size={16} aria-hidden="true" /><p>{demo.enabled ? "Local demo with synthetic data. Both workspaces are open for evaluation; progress is saved on this installation." : "Your profile and progress are visible only to you and your HR team."}</p></div>
    </div><p className="login-bottom-note">Built around your potential. Designed for your future.</p></section>
  </main>;
}

function App({ user, onSignOut }) {
  const isHr = user.role === "hr";
  const [view, setView] = useState(isHr ? "hr" : "employee");
  const [employees, setEmployees] = useState([]);
  const [employeeQuery, setEmployeeQuery] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [employeeDetail, setEmployeeDetail] = useState(null);
  const [recommendations, setRecommendations] = useState([]);
  const [hrOverview, setHrOverview] = useState(null);
  const [sessionCompletions, setSessionCompletions] = useState({});
  const [loadingEmployee, setLoadingEmployee] = useState(true);
  const [loadingRecommendations, setLoadingRecommendations] = useState(false);
  const [recommendationError, setRecommendationError] = useState("");
  const [loadingHr, setLoadingHr] = useState(false);
  const [completingEvent, setCompletingEvent] = useState("");
  const [error, setError] = useState("");
  const [uploadResult, setUploadResult] = useState(null);
  const employeeRequest = useRef(0);
  const completionRequests = useRef({});

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
    const request = ++employeeRequest.current;
    setLoadingEmployee(true);
    setLoadingRecommendations(true);
    setRecommendations([]);
    setRecommendationError("");
    setError("");
    const current = (callback) => (value) => { if (request === employeeRequest.current) callback(value); };
    await loadEmployeeResources({
      employeeId, request: apiRequest,
      onProfile: current((detail) => { setEmployeeDetail(detail); setLoadingEmployee(false); }),
      onRecommendations: current((recs) => { setRecommendations(recs.recommendations || []); setLoadingRecommendations(false); }),
      onProfileError: current((exc) => { setEmployeeDetail(null); setError(exc.message); setLoadingEmployee(false); }),
      onRecommendationError: current((exc) => { setRecommendationError(exc.message); setLoadingRecommendations(false); }),
    });
  }

  useEffect(() => {
    async function bootstrap() {
      try {
        await Promise.all([loadEmployees(), ...(isHr ? [loadHrOverview()] : [])]);
      } catch (exc) {
        setError(exc.message);
        setLoadingEmployee(false);
      }
    }
    bootstrap();
  }, [isHr]);

  useEffect(() => {
    loadEmployee(selectedId);
    return () => { employeeRequest.current += 1; };
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
    const request = employeeRequest.current;
    setCompletingEvent(recommendation.event_id);
    setError("");
    try {
      const result = await apiRequest("/complete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          employee_id: selectedId,
          event_id: recommendation.event_id,
          request_id: completionRequests.current[`${selectedId}:${recommendation.event_id}`] ||= makeRequestId(selectedId, recommendation.event_id),
        }),
      });
      delete completionRequests.current[`${selectedId}:${recommendation.event_id}`];
      if (request !== employeeRequest.current) return;
      setEmployeeDetail((current) =>
        current?.profile.employee_id === result.employee_id
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
            type: recommendation.type,
            date: employeeDetail.as_of_date,
            status: "completed",
            record_id: result.record_id,
            skill_changes: result.skill_changes,
          },
          ...(current[selectedId] || []),
        ],
      }));
      await Promise.all([loadEmployee(selectedId), ...(isHr ? [loadHrOverview()] : [])]);
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
      if (!nextId || nextId === selectedId) await loadEmployee(nextId || selectedId);
    } catch (exc) {
      setError(exc.message);
      throw exc;
    }
  }

  const employeeView = ["employee", "skills", "history"].includes(view);
  const currentProfile = employeeDetail?.profile.employee_id === selectedId ? employeeDetail : null;
  const navItems = [
    { id: "employee", label: "My development", icon: LayoutDashboard },
    { id: "skills", label: "My skills", icon: Layers3 },
    { id: "history", label: "Activity history", icon: History },
  ];
  const hrItems = [
    { id: "hr", label: "HR overview", icon: UsersRound },
    { id: "upload", label: "Upload profiles", icon: UploadCloud },
  ];
  const activeLabel = [...navItems, ...hrItems].find((item) => item.id === view)?.label;
  const displayName = isHr ? "HR workspace" : currentProfile?.profile.full_name || user.employee_id;
  function navigate(nextView) {
    setView(nextView);
    window.scrollTo({ top: 0, behavior: "instant" });
  }
  function navButton(item) {
    const Icon = item.icon;
    return <button key={item.id} type="button" className={`nav-button ${view === item.id ? "nav-button-active" : ""}`} onClick={() => navigate(item.id)} aria-current={view === item.id ? "page" : undefined}><Icon size={19} aria-hidden="true" /><span>{item.label}</span>{view === item.id && <span className="nav-active-dot" />}</button>;
  }
  return <div className="app-shell">
    <a className="skip-link" href="#main-content">Skip to content</a>
    <aside className="sidebar"><Brand /><nav aria-label="Main navigation"><span className="nav-group-label">YOUR WORKSPACE</span><div className="nav-group">{navItems.map(navButton)}</div>{isHr && <><span className="nav-group-label hr-nav-label">PEOPLE & INSIGHTS</span><div className="nav-group">{hrItems.map(navButton)}</div></>}</nav>
      <div className="sidebar-bottom"><div className="sidebar-note"><span className="sidebar-note-icon"><Route size={22} aria-hidden="true" /></span><h2>Your future.<br />One step closer.</h2><p>Every skill you build opens a new possibility.</p><span>GROW WITH PURPOSE <ArrowUpRight size={14} aria-hidden="true" /></span></div><div className="sidebar-account"><span className="avatar avatar-small" aria-hidden="true">{isHr ? "HR" : initials(displayName)}</span><span><strong>{displayName}</strong><small>{isHr ? "People & development" : "Personal workspace"}</small></span><button className="icon-button" type="button" aria-label="Sign out" onClick={() => onSignOut().catch((exc) => setError(exc.message))}><LogOut size={18} aria-hidden="true" /></button></div></div>
    </aside>
    <div className="workspace"><header className="topbar"><div className="breadcrumb"><span>Workspace</span><ChevronRight size={14} aria-hidden="true" /><strong>{activeLabel}</strong></div><div className="topbar-right"><span className="workspace-status"><span className="status-dot" />{isHr ? "HR workspace" : "Personal workspace"}</span><span className="topbar-divider" /><span className="topbar-event">HackAlem <span>AI</span></span><button className="icon-button mobile-signout" type="button" aria-label="Sign out" onClick={() => onSignOut().catch((exc) => setError(exc.message))}><LogOut size={18} aria-hidden="true" /></button></div></header>
      <main id="main-content" className="workspace-content" tabIndex={-1}>
        {error && <div role="alert" className="notice notice-error global-notice"><AlertCircle size={18} aria-hidden="true" /><span>{error}</span></div>}
        {uploadResult && view !== "upload" && <div role="status" className="notice notice-success global-notice"><Check size={18} aria-hidden="true" /><span>Imported {uploadResult.inserted.employees} employee(s) and {uploadResult.inserted.activity_history} activity record(s).</span></div>}
        {isHr && employeeView && <EmployeePicker employees={filteredEmployees} query={employeeQuery} selectedId={selectedId} total={employees.length} onQuery={setEmployeeQuery} onSelect={setSelectedId} />}
        {employeeView ? <EmployeeView detail={currentProfile} recommendations={recommendations} loading={loadingEmployee} loadingRecommendations={loadingRecommendations} recommendationError={recommendationError} onRetry={() => loadEmployee(selectedId)} completingEvent={completingEvent} completions={sessionCompletions[selectedId] || []} onComplete={markComplete} view={view} onNavigate={navigate} /> : view === "hr" && isHr ? <HrView overview={hrOverview} loading={loadingHr} onOpen={(id) => { setSelectedId(id); navigate("employee"); }} /> : view === "upload" && isHr ? <UploadPanel onUpload={handleUpload} result={uploadResult} /> : null}
      </main>
    </div>
  </div>;
}

createRoot(document.getElementById("root")).render(
  <React.StrictMode><SessionApp /></React.StrictMode>,
);
