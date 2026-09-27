"use client";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Network, Layers3 } from "lucide-react";
import { loadLiveData, loadOpportunity, type LiveData } from "@/lib/live-api";
import {
  utilityLegend,
  resolvePair,
  formatDate,
  validLocation,
  parseCalendarDate,
} from "@/lib/utils";
import {
  ALERT_DISTANCE_MILES,
  DEMO_DATE_RANGE,
  relationshipPhase,
  timingLabel,
} from "@/lib/coordination";
import { UtilityColors, COMPARISON_COLORS } from "@/components/UtilityColors";
import DistanceSlider from "@/components/controls/DistanceSlider";
import CoordinationCard from "@/components/opportunities/CoordinationCard";
import CoProcurementDossier from "@/components/opportunities/CoProcurementDossier";
import ProjectTimeline from "@/components/timeline/ProjectTimeline";
import Utility3DScene from "@/components/visualization/Utility3DScene";

export default function Home() {
  const [data, setData] = useState<LiveData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    loadLiveData(controller.signal)
      .then((value) => {
        if (!controller.signal.aborted) setData(value);
      })
      .catch((error: Error) => {
        if (!controller.signal.aborted) setError(error.message);
      });
    return () => controller.abort();
  }, [attempt]);
  if (!data)
    return (
      <main className="panel p-8 m-6" aria-live="polite">
        <h1>Synchro coordination workspace</h1>
        {error ? (
          <div role="alert">
            <h2>Could not load project data</h2>
            <p>{error}</p>
            <button
              className="primary-button"
              onClick={() => {
                setError(null);
                setAttempt((v) => v + 1);
              }}
            >
              Retry connection
            </button>
          </div>
        ) : (
          <p role="status">
            Loading projects, map features, and opportunities…
          </p>
        )}
      </main>
    );
  return <Dashboard data={data} />;
}

function Dashboard({ data }: { data: LiveData }) {
  const utilities = useMemo(
    () => utilityLegend(data.projects),
    [data.projects],
  );
  const relationships = data.matches;
  const initial = relationships[0];
  const dateRange = useMemo(() => {
    const dates = data.projects
      .flatMap((p) => [p.constructionStart, p.constructionEnd, p.inServiceDate])
      .filter((d): d is string => parseCalendarDate(d) !== null)
      .sort();
    return dates.length
      ? {
          min: dates[0].slice(0, 4) + "-01-01",
          max: dates[dates.length - 1].slice(0, 4) + "-12-31",
        }
      : DEMO_DATE_RANGE;
  }, [data.projects]);
  const maximumDistance = Math.max(
    ALERT_DISTANCE_MILES,
    Math.ceil(Math.max(0, ...relationships.map((m) => m.distanceMiles))),
  );
  const [utilityA, setUtilityA] = useState(utilities[0]?.id ?? "");
  const [utilityB, setUtilityB] = useState(utilities[1]?.id ?? "");
  const [distance, setDistance] = useState(maximumDistance);
  const [selectedDate, setSelectedDate] = useState(
    initial?.focusWindow?.start ?? dateRange.min,
  );
  const [selectedMatchId, setSelectedMatchId] = useState<string | null>(
    initial?.id ?? null,
  );
  const [dossierOpen, setDossierOpen] = useState(false);
  const projects = useMemo(
    () =>
      data.projects.filter(
        (p) => p.utilityId === utilityA || p.utilityId === utilityB,
      ),
    [utilityA, utilityB, data.projects],
  );
  const colors = useMemo(
    () => ({
      [utilityA]: COMPARISON_COLORS[0],
      [utilityB]: COMPARISON_COLORS[1],
    }),
    [utilityA, utilityB],
  );
  const compared = relationships.filter(
    (m) => resolvePair(m, projects) && m.distanceMiles <= distance,
  );
  const opportunities = compared;
  const visible = opportunities;
  const selected =
    selectedMatchId === null
      ? null
      : (visible.find((m) => m.id === selectedMatchId) ?? visible[0] ?? null);
  const [detail, setDetail] = useState<Awaited<
    ReturnType<typeof loadOpportunity>
  > | null>(null);
  const [detailError, setDetailError] = useState<{
    id: string;
    message: string;
  } | null>(null);
  const [detailAttempt, setDetailAttempt] = useState(0);
  const selectedId = selected?.id;
  useEffect(() => {
    if (!selectedId) return;
    const controller = new AbortController();
    loadOpportunity(selectedId, data.projects, controller.signal)
      .then((value) => {
        if (!controller.signal.aborted) setDetail(value);
      })
      .catch((error: Error) => {
        if (!controller.signal.aborted)
          setDetailError({ id: selectedId, message: error.message });
      });
    return () => controller.abort();
  }, [selectedId, data.projects, detailAttempt]);
  const currentDetail = detail?.match.id === selectedId ? detail : null;
  const currentError =
    detailError && detailError.id === selectedId ? detailError.message : null;
  const rawPair = selected
    ? resolvePair(selected, currentDetail?.projects ?? projects)
    : null;
  const pair = rawPair
    ? [...rawPair].sort((a) => (a.utilityId === utilityA ? -1 : 1))
    : [];
  const phase = selected
    ? relationshipPhase(selected, selectedDate)
    : "unavailable";
  const activeCount = opportunities.filter(
    (m) => relationshipPhase(m, selectedDate) === "active",
  ).length;
  const unmappable = projects.filter(
    (p) => !p.geometry && !validLocation(p.location),
  ).length;
  const openDossier = () => {
    setDossierOpen(true);
    requestAnimationFrame(() =>
      document.getElementById("dossier")?.focus({ preventScroll: false }),
    );
  };
  const selectMatch = (id: string | null) => {
    setDetail(null);
    setDetailError(null);
    setDetailAttempt(value => value + 1);
    setSelectedMatchId(id);
    setDossierOpen(false);
  };
  const selectFromMap = (id: string | null) => {
    selectMatch(id);
    if (id) setDossierOpen(true);
  };
  const changeUtility = (role: "A" | "B", value: string) => {
    if (role === "A") {
      setUtilityA(value);
      if (value === utilityB) setUtilityB(utilityA);
    } else {
      setUtilityB(value);
      if (value === utilityA) setUtilityA(utilityB);
    }
    setSelectedMatchId("first");
    setDossierOpen(false);
  };
  return (
    <UtilityColors colors={colors}>
      <a
        href="#workspace-main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-3 focus:z-50 rounded-md bg-white px-4 py-3 font-semibold text-purple-950"
      >
        Skip to coordination workspace
      </a>
      <header className="topbar">
        <Link href="/" className="brand">
          <span>
            <Network size={23} />
          </span>
          synchro<span className="brand-period">.</span>
        </Link>
        <div className="workspace-label">Coordination workspace</div>
        <nav
          aria-label="Workspace sections"
          className="workspace-nav flex items-center gap-1"
        >
          <a
            href="#coordination-map"
            className="rounded-md px-3 py-2 text-xs font-semibold transition-colors"
          >
            Map
          </a>
          <a
            href="#construction-timeline"
            className="rounded-md px-3 py-2 text-xs font-semibold transition-colors"
          >
            Timeline
          </a>
          <a
            href="#opportunities"
            className="rounded-md px-3 py-2 text-xs font-semibold transition-colors"
          >
            Opportunities
          </a>
        </nav>
        <span className="demo-badge">
          <span />
          Live API data
        </span>
        <span className="header-note">ShellHacks 2026</span>
      </header>
      <main id="workspace-main" tabIndex={-1}>
        {!data.projects.length && (
          <section className="panel p-6 my-6" role="status">
            <h2>No projects available yet</h2>
            <p>The API connection is working, but the project list is empty.</p>
            <button
              className="text-button"
              onClick={() => window.location.reload()}
            >
              Refresh data
            </button>
          </section>
        )}
        <div className="page-heading">
          <div>
            <div className="eyebrow">SHARED GROUND. BETTER TIMING.</div>
            <h1>Find the overlap.</h1>
            <p>
              Choose two utilities. Select a pair. Explore when their plans
              overlap.
            </p>
          </div>
          <div className="study-label">
            <Layers3 size={22} />
            <span>
              UTILITY PROJECTS
              <small>{projects.length} projects in this comparison</small>
            </span>
          </div>
        </div>
        <section
          className="comparison-strip panel"
          aria-label="Utility comparison"
        >
          {(["A", "B"] as const).map((role, index) => (
            <label
              className="utility-choice"
              key={role}
              style={{ borderColor: COMPARISON_COLORS[index] }}
            >
              <span style={{ color: COMPARISON_COLORS[index] }}>
                Utility {role}
              </span>
              <select
                aria-label={`Utility ${role}`}
                value={role === "A" ? utilityA : utilityB}
                onChange={(e) => changeUtility(role, e.target.value)}
              >
                {utilities.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.name}
                  </option>
                ))}
              </select>
            </label>
          ))}
          <p>
            Service-territory geometry unavailable.
            <br />
            <small>Map geometry comes from the project API.</small>
          </p>
        </section>
        <div className="dashboard judging-dashboard">
          <aside className="sidebar panel" id="opportunities">
            <div className="filter-header">
              <h2>Explore opportunities</h2>
              <button
                className="text-button"
                onClick={() => {
                  setDistance(maximumDistance);
                  setSelectedMatchId("first");
                }}
              >
                Reset filters
              </button>
            </div>
            <DistanceSlider
              value={distance}
              max={maximumDistance}
              onChange={setDistance}
            />
            <details className="rule-explainer">
              <summary>How alerts are identified</summary>
              <p>
                Opportunities and tiers come from the API. Filters narrow the
                list without changing its returned order.
              </p>
              <p>In-service dates are milestones, not construction windows.</p>
            </details>
            <div className="list-heading">
              <h2>Opportunities</h2>
              <span>{opportunities.length}</span>
            </div>
            <p className="muted small" aria-live="polite">
              {activeCount} with confirmed construction overlap at{" "}
              {formatDate(selectedDate)}
            </p>
            <div className="opportunity-list">
              {opportunities.map((match, i) => (
                <CoordinationCard
                  key={match.id}
                  match={match}
                  projects={projects}
                  selected={selected?.id === match.id}
                  selectedDate={selectedDate}
                  rank={i + 1}
                  onSelect={() => selectMatch(match.id)}
                />
              ))}
            </div>
            {!opportunities.length && (
              <div className="empty-state">
                <h3>
                  {data.matches.length
                    ? "No opportunities in this range"
                    : "No opportunities returned by the API"}
                </h3>
                <p>
                  {data.matches.length
                    ? "Try a larger distance or another utility comparison."
                    : "Matches will appear when available from the service."}
                </p>
              </div>
            )}
          </aside>
          <div className="center-column">
            <section
              className={`panel relationship-summary ${phase === "active" ? "alert-active" : ""}`}
              aria-label="Selected relationship"
              aria-live="polite"
            >
              <div>
                <div className="eyebrow">
                  {phase === "active"
                    ? "COLLISION / SYNERGY ALERT"
                    : phase === "upcoming"
                      ? "UPCOMING COORDINATION WINDOW"
                      : phase === "past"
                        ? "PAST COORDINATION WINDOW"
                        : "EXPLORE A PROJECT PAIR"}
                </div>
                <h2>
                  {pair.length === 2
                    ? `${pair[0].name} ↔ ${pair[1].name}`
                    : "Select an opportunity on the map or list."}
                </h2>
              </div>
              {selected && (
                <>
                  <div className="relationship-metrics">
                    <strong>
                      {selected.distanceMiles.toFixed(2)} mi apart
                    </strong>
                    <strong>{timingLabel(selected)}</strong>
                    <span>Explore shared access or staging</span>
                  </div>
                  <p className="muted small">
                    API distance · Tier: {selected.tier}
                    {phase === "active" &&
                    selected.gapDays !== null &&
                    selected.gapDays > 0
                      ? " · Planning gap between construction windows"
                      : ""}
                  </p>
                  <button
                    className="primary-button inline-flex items-center gap-2"
                    onClick={openDossier}
                  >
                    Open Co-Procurement Dossier →
                  </button>
                </>
              )}
            </section>
            <section className="panel scene-panel" id="coordination-map">
              <Utility3DScene
                live
                projects={projects}
                matches={visible}
                selectedDate={selectedDate}
                selectedMatchId={selected?.id ?? null}
                onSelectMatch={selectFromMap}
              />
            </section>
            {unmappable > 0 && (
              <p className="muted small">
                {unmappable} projects cannot be mapped because location data is
                missing or invalid.
              </p>
            )}
            <ProjectTimeline
              projects={pair}
              selectedDate={selectedDate}
              dateRange={dateRange}
              onDateChange={setSelectedDate}
            />
            <p className="demo-notice">
              Live API records. Proximity and timing identify areas to
              investigate; they do not verify shared infrastructure or
              procurement feasibility.
            </p>
          </div>
        </div>
        <details className="panel p-6 my-6">
          <summary className="font-semibold cursor-pointer">
            All API projects ({data.projects.length})
          </summary>
          <div className="overflow-x-auto mt-4">
            <table className="w-full text-left text-sm">
              <thead>
                <tr>
                  {[
                    "Project",
                    "Utility",
                    "Location",
                    "Status",
                    "In-service milestone",
                    "Validation",
                  ].map((label) => (
                    <th className="p-3" key={label} scope="col">
                      {label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.projects.map((p) => (
                  <tr key={p.id} className="border-t border-slate-200">
                    <th className="p-3" scope="row">
                      {p.name}
                      <small className="block font-normal">
                        {p.id}
                        {p.synthetic ? " · Synthetic fixture" : ""}
                      </small>
                    </th>
                    <td className="p-3">{p.utilityName}</td>
                    <td className="p-3">{p.locationText || "Unavailable"}</td>
                    <td className="p-3">{p.status}</td>
                    <td className="p-3">
                      {p.inServiceDate
                        ? formatDate(p.inServiceDate)
                        : "Not provided"}
                    </td>
                    <td className="p-3">{p.validationState}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
        {dossierOpen && selected && (
          <div aria-live="polite">
            {currentError ? (
              <div className="panel p-6" role="alert">
                <p>Could not load match details: {currentError}</p>
                <button
                  className="primary-button"
                  onClick={() => {
                    setDetailError(null);
                    setDetailAttempt((v) => v + 1);
                  }}
                >
                  Retry details
                </button>
              </div>
            ) : currentDetail ? (
              <CoProcurementDossier
                match={currentDetail.match}
                projects={currentDetail.projects}
                selectedDate={selectedDate}
                onClose={() => setDossierOpen(false)}
              />
            ) : (
              <p className="panel p-6" role="status">
                Loading match details…
              </p>
            )}
          </div>
        )}
        <footer>
          Synchro / ShellHacks 2026<span>Connected to Gridlock API</span>
        </footer>
      </main>
    </UtilityColors>
  );
}
