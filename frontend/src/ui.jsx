import React, { useState } from "react";
import {
  AlertCircle, ArrowRight, ArrowUpRight, BarChart3, BookOpen, BriefcaseBusiness,
  CalendarDays, Check, CheckCircle2, ChevronDown, Clock3, FileJson, FileUp,
  Flag, GraduationCap, History, Layers3, MapPin, RefreshCw, Route, Search,
  ShieldCheck, Sparkles, Target, TrendingUp, UploadCloud, UsersRound,
} from "lucide-react";

export function formatNumber(value, digits = 3) {
  if (value === null || value === undefined || value === "") return "—";
  return typeof value === "number" ? String(Number(value.toFixed(digits))) : value;
}

export function formatDate(value) {
  if (!value) return "Any time";
  return new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }).format(new Date(`${value}T00:00:00Z`));
}

export function initials(name = "") {
  return name.trim().split(/\s+/).slice(0, 2).map((part) => part[0]).join("").toUpperCase();
}

export function Brand({ light = false }) {
  return <div className={`brand ${light ? "brand-light" : ""}`}>
    <span className="brand-mark" aria-hidden="true"><Route size={23} strokeWidth={2.2} /></span>
    <span>career<span className="brand-light-word">quest</span><span className="brand-caption">A LITTLE STEP. A BIG FUTURE.</span></span>
  </div>;
}

export function Pill({ children, tone = "slate" }) {
  const tones = { slate: "pill-slate", green: "pill-green", amber: "pill-amber", blue: "pill-blue", red: "pill-red" };
  return <span className={`pill ${tones[tone] || tones.slate}`}>{children}</span>;
}

export function PageHeading({ eyebrow, title, description, children }) {
  return <header className="page-heading">
    <div>{eyebrow && <p className="eyebrow">{eyebrow}</p>}<h1>{title}</h1>{description && <p className="page-description">{description}</p>}</div>
    {children && <div className="page-heading-action">{children}</div>}
  </header>;
}

export function EmptyState({ icon: Icon = GraduationCap, title, body }) {
  return <div className="empty-state"><span className="empty-icon"><Icon size={24} aria-hidden="true" /></span><div><h3>{title}</h3>{body && <p>{body}</p>}</div></div>;
}

function Stat({ label, value, detail, icon: Icon = Target, tone = "green" }) {
  const tones = { green: "icon-green", blue: "icon-blue", amber: "icon-amber" };
  return <div className="stat-cell"><div><p className="stat-label">{label}</p><p className="stat-value">{value}</p><p className="stat-detail">{detail}</p></div><span className={`stat-icon ${tones[tone]}`}><Icon size={21} aria-hidden="true" /></span></div>;
}

export function EmployeePicker({ employees, query, selectedId, total, onQuery, onSelect }) {
  const hasSelection = employees.some((employee) => employee.id === selectedId);
  return <section className="employee-picker" aria-label="Select an employee">
    <div className="picker-intro"><UsersRound size={20} aria-hidden="true" /><span>Employee workspace<small>{total} profiles available</small></span></div>
    <div className="picker-fields"><div className="search-input"><Search size={16} aria-hidden="true" /><label className="sr-only" htmlFor="employee-search">Search employees</label><input id="employee-search" value={query} onChange={(event) => onQuery(event.target.value)} placeholder="Name, role or department…" /></div>
      <label className="sr-only" htmlFor="employee-select">Employee profile</label><select id="employee-select" className="input" value={hasSelection ? selectedId : ""} onChange={(event) => onSelect(event.target.value)}>
        {!hasSelection && <option value="" disabled>{employees.length ? "Choose a matching profile" : "No matching employees"}</option>}
        {employees.map((employee) => <option key={employee.id} value={employee.id}>{employee.name} · {employee.id}</option>)}
      </select></div>
  </section>;
}

export function UploadPanel({ onUpload, result }) {
  const [employeesFile, setEmployeesFile] = useState(null);
  const [historyFile, setHistoryFile] = useState(null);
  const [jsonText, setJsonText] = useState("");
  const [uploading, setUploading] = useState(false);
  const [mode, setMode] = useState("files");
  const [localError, setLocalError] = useState("");
  async function submit(event) {
    event.preventDefault(); setLocalError(""); setUploading(true);
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
    } catch (exc) { setLocalError(exc.message); }
    finally { setUploading(false); }
  }
  return <div className="page-enter">
    <PageHeading eyebrow="PEOPLE OPERATIONS" title="More people. More possibilities." description="Bring new profiles and activity history into your development workspace." />
    <div className="upload-layout"><section className="panel upload-panel">
      <div className="section-heading"><div><h2>Import your data</h2><p>Upload files or paste a JSON batch to get started.</p></div><span className="stat-icon icon-green"><UploadCloud size={22} aria-hidden="true" /></span></div>
      <div className="segmented-control" aria-label="Upload format">{["files", "json"].map((item) => <button type="button" key={item} className={`segmented-button ${mode === item ? "segmented-button-active" : ""}`} aria-pressed={mode === item} onClick={() => setMode(item)}>{item === "files" ? <FileUp size={16} aria-hidden="true" /> : <FileJson size={16} aria-hidden="true" />}{item === "files" ? "Files" : "JSON"}</button>)}</div>
      <form onSubmit={submit} className="upload-form">
        {mode === "files" ? <div className="upload-files">{[
          { id: "employees-file", label: "Employee profiles", hint: "Choose an employees JSON file", accept: ".json,application/json", file: employeesFile, set: setEmployeesFile, type: "JSON" },
          { id: "history-file", label: "Activity history", hint: "Choose an activity history CSV", accept: ".csv,text/csv", file: historyFile, set: setHistoryFile, type: "CSV" },
        ].map((item) => <label key={item.id} className={`file-drop ${item.file ? "file-selected" : ""}`} htmlFor={item.id}>
          <span className="file-icon">{item.file ? <CheckCircle2 size={26} aria-hidden="true" /> : <FileUp size={26} aria-hidden="true" />}</span><strong>{item.label}</strong><span className="file-name">{item.file?.name || item.hint}</span><span className="pill">{item.type} · Browse files</span>
          <input id={item.id} className="sr-only" type="file" accept={item.accept} onChange={(event) => item.set(event.target.files?.[0] || null)} />
        </label>)}</div> : <div><label htmlFor="json-batch" className="field-label">JSON batch</label><textarea id="json-batch" className="input json-input" value={jsonText} onChange={(event) => setJsonText(event.target.value)} placeholder={'{\n  "employees": [],\n  "activity_history": []\n}'} spellCheck={false} /></div>}
        {localError && <p role="alert" className="notice notice-error"><AlertCircle size={18} aria-hidden="true" />{localError}</p>}
        {result && <p role="status" className="notice notice-success"><CheckCircle2 size={18} aria-hidden="true" />Added {result.inserted.employees} employee(s) and {result.inserted.activity_history} history record(s).</p>}
        <div className="upload-footer"><span><ShieldCheck size={15} aria-hidden="true" />Validated before import</span><button type="submit" className="primary-button" disabled={uploading}>{uploading ? <RefreshCw size={17} className="animate-spin" aria-hidden="true" /> : <UploadCloud size={17} aria-hidden="true" />}{uploading ? "Importing…" : "Upload and open"}</button></div>
      </form>
    </section><aside className="upload-guide"><span className="eyebrow">A SMOOTH START</span><h2>From profile<br />to possibility.</h2><ol><li><span>01</span><div><h3>Prepare your files</h3><p>Use the dataset schema for employee profiles and participation records. Either file can be uploaded on its own.</p></div></li><li><span>02</span><div><h3>Let us check the details</h3><p>Skills, roles and activity references are validated together. Existing profiles stay intact.</p></div></li><li><span>03</span><div><h3>Explore the next step</h3><p>The first new profile opens automatically, with its own career path and recommendations.</p></div></li></ol><div className="guide-note"><FileJson size={18} aria-hidden="true" /><p>JSON batches use <code>employees</code> and <code>activity_history</code> arrays. Maximum upload size: 2 MiB.</p></div></aside></div>
  </div>;
}

function ProgressRing({ value }) {
  const safeValue = Math.max(0, Math.min(100, value));
  return <div className="progress-ring" role="img" aria-label={`${formatNumber(value, 2)}% of target skill levels met`}>
    <svg viewBox="0 0 120 120" aria-hidden="true"><circle className="ring-track" cx="60" cy="60" r="51" /><circle className="ring-value" cx="60" cy="60" r="51" pathLength="100" strokeDasharray={`${safeValue} 100`} /></svg><span><strong>{formatNumber(value, 1)}<small>%</small></strong><em>of target levels</em></span>
  </div>;
}

function ProfileHero({ profile, trajectory }) {
  return <section className="profile-hero" aria-label="Profile and career trajectory">
    <div className="profile-intro"><div className="profile-identity"><span className="avatar avatar-large" aria-hidden="true">{initials(profile.full_name)}</span><div><p className="eyebrow">YOUR POTENTIAL, IN PROGRESS</p><h2>{profile.full_name}</h2><p>{profile.role} <span className="inline-dot">·</span> {profile.grade}</p></div></div>
      <div className="profile-meta"><span><BriefcaseBusiness size={15} aria-hidden="true" />{profile.department}</span><span><MapPin size={15} aria-hidden="true" />{profile.work_format}</span><span><CalendarDays size={15} aria-hidden="true" />{profile.tenure_months} months here</span></div>
      <div className="profile-footnote"><span className="status-dot" />Profile {profile.employee_id}<span>Last review · {formatDate(profile.last_review_date)}</span></div>
    </div>
    <div className="trajectory-card"><div><span className="trajectory-eyebrow"><Flag size={13} aria-hidden="true" /> YOUR NEXT CHAPTER</span><h3>{trajectory.target_grade}<br /><span>{trajectory.target_role}</span></h3><p>{profile.grade} <ArrowRight size={14} aria-hidden="true" /> {trajectory.target_grade}</p></div><ProgressRing value={trajectory.progress_pct} /></div>
  </section>;
}

function SkillRows({ skills, preview = false }) {
  return <div className={`skill-list ${preview ? "skill-list-preview" : ""}`}>{skills.map((skill) => <div className="skill-row" key={skill.skill_id}>
    <div className="skill-name"><strong>{skill.skill_name}</strong>{skill.critical ? <span className="critical-label"><span />Critical for growth</span> : <span>Supporting skill</span>}</div>
    <div className="skill-levels"><div className="skill-bars" role="img" aria-label={`Current level ${skill.current}, required level ${skill.required}, out of 5`}>{[1, 2, 3, 4, 5].map((level) => <span key={level} className={level <= skill.current ? "level-current" : level <= skill.required ? "level-needed" : "level-unused"} />)}</div><span><strong>{formatNumber(skill.current)}</strong> / {formatNumber(skill.required)} required</span></div>
    <div className="skill-gap">{skill.gap ? <Pill tone="amber">{formatNumber(skill.gap)} to go</Pill> : <Pill tone="green"><Check size={12} aria-hidden="true" />Target met</Pill>}</div>
  </div>)}</div>;
}

function SkillsPanel({ trajectory, preview = false, onNavigate }) {
  const skills = [...trajectory.skills].sort((a, b) => Number(b.critical) - Number(a.critical) || b.gap - a.gap);
  return <section className="panel"><div className="section-heading"><div><h2>{preview ? "Skills to move you forward" : "Your skills, mapped out"}</h2><p>{preview ? "Focus on what matters for your next role." : `Current levels compared with ${trajectory.target_grade} ${trajectory.target_role} requirements.`}</p></div>{preview && <button className="text-button" onClick={() => onNavigate("skills")}>View all <ArrowUpRight size={15} aria-hidden="true" /></button>}</div>
    <SkillRows skills={preview ? skills.slice(0, 5) : skills} preview={preview} />
    <div className="skill-legend"><span><i className="legend-current" />Current level</span><span><i className="legend-needed" />Target gap</span><span>Scale 0–5</span></div>
  </section>;
}

function HistoryPanel({ activities, preview = false, onNavigate }) {
  const [filter, setFilter] = useState("all");
  const filtered = activities.filter((item) => filter === "all" || item.status === filter);
  const rows = preview ? activities.slice(0, 4) : filtered;
  return <section className="panel"><div className="section-heading"><div><h2>{preview ? "Your recent activity" : "Every step counts"}</h2><p>{preview ? "A look at your learning journey." : `${activities.filter((item) => item.status === "completed").length} completed · ${activities.length} activities recorded`}</p></div>{preview && <button className="text-button" onClick={() => onNavigate("history")}>View all <ArrowUpRight size={15} aria-hidden="true" /></button>}</div>
    {!preview && <div className="history-filter"><label htmlFor="history-status">Filter by status</label><select id="history-status" className="input" value={filter} onChange={(event) => setFilter(event.target.value)}><option value="all">All activities</option>{[...new Set(activities.map((item) => item.status))].sort().map((status) => <option key={status} value={status}>{status.replaceAll("_", " ")}</option>)}</select><span aria-live="polite">{filtered.length} activities</span></div>}
    {rows.length ? <ul className="history-list" aria-label="Activity history">{rows.map((item) => <li key={item.record_id} className="history-row"><span className={`history-icon ${item.status === "completed" ? "history-icon-completed" : ""}`}>{item.status === "completed" ? <CheckCircle2 size={18} aria-hidden="true" /> : <Clock3 size={18} aria-hidden="true" />}</span><div className="history-content"><h3>{item.title}</h3><p><time dateTime={item.date}>{formatDate(item.date)}</time><span>·</span>{item.type.replaceAll("_", " ")}{!preview && <><span>·</span>{item.event_id}</>}</p>{item.skill_changes?.length > 0 && <div className="skill-changes">{item.skill_changes.map((change) => <Pill key={change.skill_id} tone={change.gain > 0 ? "green" : "slate"}>{change.skill_id}: {formatNumber(change.before)} → {formatNumber(change.after)}</Pill>)}</div>}</div><Pill tone={item.status === "completed" ? "green" : item.status === "in_progress" ? "blue" : "amber"}>{item.status.replaceAll("_", " ")}</Pill></li>)}</ul> : <EmptyState icon={History} title="A fresh start" body="Your activity history will appear here as you take your next steps." />}
  </section>;
}

export function EmployeeView({ detail, recommendations, loading, loadingRecommendations, recommendationError, onRetry, completingEvent, completions, onComplete, view, onNavigate }) {
  if (loading && !detail) return <Skeleton title="Getting your workspace ready" />;
  if (!detail) return <EmptyState title="Your next chapter is waiting" body="Select an employee profile to explore their development journey." />;
  const { profile, trajectory } = detail;
  const historyById = new Map((detail.activity_history || []).map((item) => [item.record_id, item]));
  for (const item of completions) historyById.set(item.record_id, { ...historyById.get(item.record_id), ...item });
  const activities = [...historyById.values()].sort((a, b) => b.date.localeCompare(a.date) || b.record_id.localeCompare(a.record_id));
  const completedCount = activities.filter((item) => item.status === "completed").length;
  const heading = view === "skills" ? { title: "Make your potential visible.", description: "See where you stand, and what will take you further." } : view === "history" ? { title: "Look how far you’ve come.", description: "Your learning, participation and progress, all in one place." } : { title: "Your growth, in focus.", description: "A clear direction. Meaningful steps. A career that moves forward." };
  return <div className="page-enter" key={view}>
    <PageHeading eyebrow={view === "employee" ? "YOUR DEVELOPMENT SPACE" : `${profile.full_name} · ${profile.grade}`} {...heading}><span className="date-label"><CalendarDays size={15} aria-hidden="true" />{formatDate(detail.as_of_date)}</span></PageHeading>
    {view === "skills" ? <><div className="stats-grid"><Stat label="Target coverage" value={`${formatNumber(trajectory.progress_pct, 1)}%`} detail="of required skill levels" icon={TrendingUp} /><Stat label="Levels to develop" value={trajectory.total_gap} detail="across your target skills" icon={Layers3} tone="blue" /><Stat label="Critical skill gap" value={trajectory.critical_gap} detail="levels that matter most" icon={Target} tone="amber" /></div><SkillsPanel trajectory={trajectory} /></> : view === "history" ? <HistoryPanel activities={activities} /> : <>
      <ProfileHero profile={profile} trajectory={trajectory} />
      <div className="stats-grid"><Stat label="Levels to develop" value={trajectory.total_gap} detail="to reach your target requirements" icon={Layers3} tone="blue" /><Stat label="Critical skill gap" value={trajectory.critical_gap} detail="focus areas for your next role" icon={Target} tone="amber" /><Stat label="Activities completed" value={completedCount} detail={`across ${activities.length} participation records`} icon={CheckCircle2} /></div>
      <section className="recommendations-section" aria-labelledby="recommendations-heading"><div className="section-heading"><div><span className="eyebrow">CURATED AROUND YOU</span><h2 id="recommendations-heading">Your recommended next steps</h2><p>Matched to your goals, skill gaps and the way you learn.</p></div>{!loadingRecommendations && !recommendationError && <Pill tone="green"><Sparkles size={13} aria-hidden="true" />{recommendations.length} {recommendations.length === 1 ? "opportunity" : "opportunities"}</Pill>}</div>
        {loadingRecommendations ? <Skeleton title="Finding your next steps" /> : recommendationError ? <div role="alert" className="panel"><p className="error-text">{recommendationError}</p><button className="secondary-button" onClick={onRetry}><RefreshCw size={15} aria-hidden="true" />Retry recommendations</button></div> : recommendations.length ? <div className="recommendation-grid">{recommendations.map((recommendation, index) => <RecommendationCard key={recommendation.event_id} recommendation={recommendation} rank={index + 1} completing={completingEvent === recommendation.event_id} disabled={Boolean(completingEvent)} onComplete={() => onComplete(recommendation)} />)}</div> : <EmptyState title="No recommended step right now" body="There are no eligible activities with a positive benefit for your current target. Review your path with HR to explore what comes next." />}
      </section>
      <div className="overview-bottom"><SkillsPanel trajectory={trajectory} preview onNavigate={onNavigate} /><HistoryPanel activities={activities} preview onNavigate={onNavigate} /></div>
      <div className="workspace-footnote"><ShieldCheck size={15} aria-hidden="true" /><span>Built around your skills. Explained with real evidence.</span><span>Career Quest · HackAlem AI</span></div>
    </>}
  </div>;
}

function RecommendationCard({ recommendation, rank, completing, disabled, onComplete }) {
  const factors = recommendation.factors;
  const engagement = factors.engagement;
  const Icon = recommendation.type === "mentoring" ? UsersRound : recommendation.type === "meetup" ? UsersRound : recommendation.type === "workshop" ? Layers3 : BookOpen;
  const nextDate = recommendation.upcoming_sessions?.[0];
  return <article className={`recommendation-card ${["recommendation-1", "recommendation-2", "recommendation-3"][rank - 1] || ""}`}>
    <div className="recommendation-top"><span className="course-icon"><Icon size={23} aria-hidden="true" /></span><span className="rank-label">{rank === 1 ? <><Sparkles size={12} aria-hidden="true" />Top recommendation</> : `0${rank} / Recommended`}</span></div>
    <div className="course-category">{recommendation.type.replaceAll("_", " ")}<span>·</span>{recommendation.format.replaceAll("_", " ")}</div><h3>{recommendation.title}</h3>
    <p className="course-meta"><span><Clock3 size={14} aria-hidden="true" />{formatNumber(recommendation.duration_hours)} hours</span><span><CalendarDays size={14} aria-hidden="true" />{nextDate ? formatDate(nextDate) : recommendation.format === "self_paced" ? "At your own pace" : "Date to be confirmed"}</span></p>
    <div className="recommendation-skill-tags">{factors.gaps.map((gap) => <span key={gap.skill_id}>+{formatNumber(gap.effective_gain)} {gap.skill_name}</span>)}</div>
    <div className="score-strip" aria-label="Recommendation factors"><div><span>Skill benefit</span><strong>{formatNumber(factors.benefit)}</strong></div><span className="score-operator">×</span><div><span>Engagement</span><strong>{formatNumber(engagement.multiplier)}</strong></div><span className="score-operator">=</span><div><span>Score</span><strong>{formatNumber(recommendation.score)}</strong></div></div>
    <details className="recommendation-details"><summary><span><ShieldCheck size={16} aria-hidden="true" />Why this fits you</span><ChevronDown size={15} aria-hidden="true" /></summary><div className="recommendation-evidence">
      <h4>Your target</h4><p>{factors.target_grade} · skill gaps and participation history shape this recommendation.</p>
      <h4>Skill contribution</h4>{factors.gaps.map((gap) => <div className="evidence-skill" key={gap.skill_id}><strong>{gap.skill_name}</strong><span>{gap.current} → {gap.required} required · gap {gap.gap}</span><span>Useful gain +{formatNumber(gap.effective_gain)}{gap.critical ? " · Critical skill" : " · Supporting skill"}</span>{gap.weight !== undefined && <span>Weight {formatNumber(gap.weight)}{gap.contribution !== undefined ? ` · Contribution ${formatNumber(gap.contribution)}` : ""}</span>}</div>)}
      <h4>Your engagement with {engagement.type}s</h4><dl className="engagement-list"><div><dt>Skipped / declined / dropped</dt><dd>{engagement.skip_count}</dd></div><div><dt>Self-initiated completions</dt><dd>{engagement.self_completion_count}</dd></div><div><dt>Self-completion factor</dt><dd>{formatNumber(engagement.self_factor)}×</dd></div><div><dt>Engagement multiplier</dt><dd>{formatNumber(engagement.multiplier)}×</dd></div></dl>
      <h4>The reasoning</h4><p className="rationale">{recommendation.rationale}</p><p className="explanation-source">Explanation: {recommendation.explanation.source}{recommendation.explanation.fallback_reason ? ` · ${recommendation.explanation.fallback_reason.replaceAll("_", " ")}` : ""}</p>
      <GatewayList gateways={recommendation.gateway_to || []} /><span className="event-reference">Activity reference · {recommendation.event_id}</span>
    </div></details>
    <button type="button" className={rank === 1 ? "primary-button complete-button" : "secondary-button complete-button"} disabled={disabled} onClick={onComplete} aria-label={`Mark ${recommendation.title} complete`}>{completing ? <RefreshCw size={17} className="animate-spin" aria-hidden="true" /> : <CheckCircle2 size={17} aria-hidden="true" />}{completing ? "Updating your progress…" : "Mark complete"}<ArrowRight size={16} aria-hidden="true" /></button>
  </article>;
}

function GatewayList({ gateways }) {
  if (!gateways.length) return null;
  return <div className="gateway-list"><h4><Route size={15} aria-hidden="true" />Where this can take you</h4>{gateways.map((gateway) => <div key={gateway.event_id}><strong>{gateway.title}</strong><p>{gateway.unlocked_after_completion ? "Available after completion" : "Progress toward prerequisites"}</p>{gateway.blocking_prerequisites.map((blocker) => <p key={blocker.skill_id}>{blocker.skill_name}: {formatNumber(blocker.current)} → {formatNumber(blocker.after_completion)} · requires {formatNumber(blocker.required)}</p>)}</div>)}</div>;
}

export function HrView({ overview, loading, onOpen }) {
  const [showAllParticipation, setShowAllParticipation] = useState(false);
  if (loading && !overview) return <Skeleton title="Preparing your people overview" />;
  if (!overview) return <EmptyState title="Your people overview is loading" body="Aggregate insights will appear here when available." />;
  const lagging = overview.most_lagging_skills.slice(0, 10);
  const participation = [...overview.participation_by_activity].sort((a, b) => b.records - a.records || a.event_id.localeCompare(b.event_id)).slice(0, showAllParticipation ? overview.participation_by_activity.length : 12);
  const maxGap = Math.max(...lagging.map((skill) => skill.total_gap), 1);
  const noStep = overview.employees_without_recommendation;
  const covered = overview.employee_count - noStep.count;
  return <div className="page-enter"><PageHeading eyebrow="THE BIG PICTURE" title="Grow people. Grow possibilities." description="Understand skill gaps, spot opportunities and support every next step."><span className="date-label"><CalendarDays size={15} aria-hidden="true" />{formatDate(overview.as_of_date)}</span></PageHeading>
    <div className="stats-grid"><Stat label="People in your workspace" value={overview.employee_count} detail="individual career journeys" icon={UsersRound} /><Stat label="Without a next step" value={noStep.count} detail="profiles to review together" icon={Route} tone="amber" /><Stat label="Skills to strengthen" value={overview.most_lagging_skills.length} detail="skills with a target gap" icon={TrendingUp} tone="blue" /></div>
    <div className="hr-insight"><span className="stat-icon"><Sparkles size={23} aria-hidden="true" /></span><div><h2>A next step for {covered} of {overview.employee_count} people.</h2><p>Recommendations connect individual goals with relevant development activities.</p></div><span className="coverage-number">{overview.employee_count ? formatNumber(covered / overview.employee_count * 100, 1) : 0}<small>% coverage</small></span></div>
    <section className="panel"><div className="section-heading"><div><span className="eyebrow">DEVELOPMENT PRIORITIES</span><h2>Where growth matters most</h2><p>Top 10 skill gaps by total missing levels across your people.</p></div><Target size={22} className="muted-icon" aria-hidden="true" /></div><div className="gap-chart">{lagging.length ? lagging.map((skill, index) => <div className="gap-chart-row" key={skill.skill_id}><span className="chart-rank">{String(index + 1).padStart(2, "0")}</span><div className="chart-skill"><strong>{skill.skill_name}</strong><span>{skill.employees_affected} people · {skill.critical_employees} with a critical gap</span></div><div className="chart-bar" aria-hidden="true"><span style={{ width: `${skill.total_gap / maxGap * 100}%` }} /></div><strong className="chart-value">{skill.total_gap}<small>levels</small></strong></div>) : <EmptyState title="Target skills are covered" body="There are no remaining target skill gaps in this workspace." />}</div></section>
    <section className="panel"><div className="section-heading"><div><span className="eyebrow">A LITTLE EXTRA ATTENTION</span><h2>People without a recommended step</h2><p>Review their target or arrange a suitable development activity.</p></div><Pill tone="amber">{noStep.count} people</Pill></div>{noStep.employees.length ? <div className="table-scroll" tabIndex={0} role="region" aria-label="Employees without a recommended step"><table className="data-table"><thead><tr><th scope="col">Employee</th><th scope="col">Current role</th><th scope="col">Career target</th><th scope="col">Skill gap</th><th scope="col">Reason</th><th scope="col"><span className="sr-only">Open profile</span></th></tr></thead><tbody>{noStep.employees.map((employee) => <tr key={employee.employee_id}><td><div className="table-person"><span className="avatar avatar-small" aria-hidden="true">{initials(employee.name)}</span><span><strong>{employee.name}</strong><small>{employee.employee_id}</small></span></div></td><td>{employee.role}<small>{employee.grade}</small></td><td>{employee.target_role}<small>{employee.target_grade}</small></td><td><strong>{employee.total_gap} total</strong><small>{employee.critical_gap} critical</small></td><td><Pill tone={employee.reason === "target_met" ? "green" : "amber"}>{employee.reason === "target_met" ? "Target met" : "No eligible activity"}</Pill></td><td><button type="button" className="icon-button" aria-label={`Open ${employee.name}`} onClick={() => onOpen(employee.employee_id)}><ArrowUpRight size={18} aria-hidden="true" /></button></td></tr>)}</tbody></table></div> : <EmptyState icon={CheckCircle2} title="Everyone has a next step" body="All profiles have an eligible development opportunity." />}</section>
    <section className="panel"><div className="section-heading"><div><span className="eyebrow">LEARNING IN MOTION</span><h2>Participation by activity</h2><p>{showAllParticipation ? "All activities" : "The 12 most active programs"}, with participation and completion counts.</p></div><button type="button" className="text-button" aria-expanded={showAllParticipation} onClick={() => setShowAllParticipation(!showAllParticipation)}>{showAllParticipation ? "Show top 12" : `View all ${overview.participation_by_activity.length} activities`}<BarChart3 size={18} aria-hidden="true" /></button></div><div className="table-scroll" tabIndex={0} role="region" aria-label="Participation by activity"><table className="data-table"><thead><tr><th scope="col">Activity</th><th scope="col">Type</th><th scope="col">Records</th><th scope="col">People</th><th scope="col">Participation breakdown</th></tr></thead><tbody>{participation.map((activity) => <tr key={activity.event_id}><td><strong>{activity.title}</strong><small>{activity.event_id}</small></td><td><span className="capitalize">{activity.type}</span></td><td className="numeric-cell">{activity.records}</td><td className="numeric-cell">{activity.participants}</td><td><div className="status-counts">{Object.entries(activity.status_counts).map(([status, count]) => <Pill key={status} tone={status === "completed" ? "green" : status === "in_progress" ? "blue" : "slate"}>{status.replaceAll("_", " ")} <strong>{count}</strong></Pill>)}</div></td></tr>)}</tbody></table></div></section>
  </div>;
}

export function Skeleton({ title }) {
  return <section className="panel skeleton" role="status" aria-label={title}><div className="skeleton-heading"><RefreshCw size={19} className="animate-spin" aria-hidden="true" /><p>{title}</p></div><div className="skeleton-line" /><div className="skeleton-line short" /><div className="skeleton-block" /></section>;
}
