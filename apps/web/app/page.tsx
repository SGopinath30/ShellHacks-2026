"use client";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useState } from "react";
import {
  Layers3,
  SlidersHorizontal,
  RotateCcw,
  ArrowRight,
  Network,
} from "lucide-react";
import { getDemoData } from "@/lib/api";
import {
  DEFAULT_FILTERS,
  filterMatches,
  resolveSelection,
  resolvePair,
  utilityColor,
} from "@/lib/utils";
import DistanceSlider from "@/components/controls/DistanceSlider";
import OverlapSlider from "@/components/controls/OverlapSlider";
import OpportunityList from "@/components/opportunities/OpportunityList";
import MatchDetails from "@/components/opportunities/MatchDetails";
import ProjectTimeline from "@/components/timeline/ProjectTimeline";
const GridMap = dynamic(() => import("@/components/map/GridMap"), {
  ssr: false,
  loading: () => <div className="map-canvas map-loading">Loading map…</div>,
});
const data = getDemoData();
export default function Home() {
  const [filters, setFilters] = useState(DEFAULT_FILTERS);
  const [selectedMatchId, setSelectedMatchId] = useState<string | null>(
    data.matches[0]?.id ?? null,
  );
  const { opportunities, unknown } = filterMatches(
    data.matches,
    filters,
    data.projects,
  );
  const visible = [...opportunities, ...unknown];
  const effectiveId = resolveSelection(selectedMatchId, visible);
  const selected = visible.find((m) => m.id === effectiveId) ?? null;
  const pair = selected ? resolvePair(selected, data.projects) : [];
  const updateFilters = (next: typeof filters) => {
    const result = filterMatches(data.matches, next, data.projects);
    setFilters(next);
    setSelectedMatchId(
      resolveSelection(selectedMatchId, [
        ...result.opportunities,
        ...result.unknown,
      ]),
    );
  };
  const selectProject = useCallback(
    (id: string) => {
      const result = filterMatches(data.matches, filters, data.projects);
      const match = [...result.opportunities, ...result.unknown].find((m) =>
        m.projectIds.includes(id),
      );
      if (match) setSelectedMatchId(match.id);
    },
    [filters],
  );
  return (
    <>
      <header className="topbar">
        <Link href="/" className="brand">
          <span>
            <Network size={23} />
          </span>
          synchro<span className="brand-period">.</span>
        </Link>
        <div className="workspace-label">Coordination workspace</div>
        <span className="demo-badge">
          <span />
          Demo data
        </span>
        <span className="header-note">ShellHacks 2026</span>
      </header>
      <main>
        <div className="page-heading">
          <div>
            <div className="eyebrow">SHARED GROUND. BETTER TIMING.</div>
            <h1>Find the overlap.</h1>
            <p>
              Discover where utility plans meet — and where collaboration can
              begin.
            </p>
          </div>
          <div className="study-label">
            <MapSymbol />{" "}
            <span>
              MIAMI STUDY AREA
              <small>7 synthetic projects · 3 fictional utilities</small>
            </span>
          </div>
        </div>
        <div className="dashboard">
          <aside className="sidebar panel">
            <div className="filter-header">
              <h2>
                <SlidersHorizontal size={17} /> Refine opportunities
              </h2>
              <button
                className="icon-button"
                title="Reset filters"
                aria-label="Reset filters"
                onClick={() => updateFilters(DEFAULT_FILTERS)}
              >
                <RotateCcw size={16} />
              </button>
            </div>
            <DistanceSlider
              value={filters.distance}
              onChange={(distance) => updateFilters({ ...filters, distance })}
            />
            <OverlapSlider
              value={filters.overlap}
              onChange={(overlap) => updateFilters({ ...filters, overlap })}
            />
            <p className="filter-note">
              Different utilities. Nearby locations.
              <br />
              Overlapping construction dates.
            </p>
            <div className="list-heading">
              <h2>Opportunities</h2>
              <span>{opportunities.length.toString().padStart(2, "0")}</span>
            </div>
            {opportunities.length ? (
              <OpportunityList
                matches={opportunities}
                projects={data.projects}
                selectedId={effectiveId}
                onSelect={setSelectedMatchId}
              />
            ) : (
              <div className="empty-state">
                <Layers3 size={28} />
                <h3>No opportunities in this range</h3>
                <p>Try a larger distance or a shorter minimum overlap.</p>
                <button
                  className="text-button"
                  onClick={() => updateFilters(DEFAULT_FILTERS)}
                >
                  Reset filters <ArrowRight size={14} />
                </button>
              </div>
            )}
            <div className="unknown-heading">
              <h3>Nearby — timing unknown</h3>
              <span>{unknown.length}</span>
            </div>
            <p className="muted small">
              Nearby pairs needing schedule evidence. These are not confirmed
              opportunities.
            </p>
            <OpportunityList
              matches={unknown}
              projects={data.projects}
              selectedId={effectiveId}
              onSelect={setSelectedMatchId}
            />
            {!unknown.length && (
              <p className="muted small">
                No nearby pairs with missing schedules.
              </p>
            )}
          </aside>
          <div className="center-column">
            <section className="map-panel panel">
              <div className="map-header">
                <h2>
                  <Layers3 size={17} /> Project landscape
                </h2>
                <span className="mini-badge">
                  {data.projects.length} projects
                </span>
              </div>
              <GridMap
                projects={data.projects}
                selectedIds={pair?.map((p) => p.id) ?? []}
                onSelect={selectProject}
              />
              <div className="map-legend">
                {["lumen", "tide", "ember"].map((id) => (
                  <span key={id}>
                    <i style={{ background: utilityColor(id) }} />
                    {data.projects.find((p) => p.utilityId === id)!.utilityName}
                  </span>
                ))}
              </div>
            </section>
            <ProjectTimeline projects={pair} />
            <div className="demo-notice">
              <span>i</span>
              <p>
                <strong>A workspace for possibilities.</strong> All records and
                evidence are synthetic. Matches illustrate proximity and timing,
                not verified engineering feasibility.
              </p>
            </div>
          </div>
          <MatchDetails match={selected} projects={data.projects} />
        </div>
        <footer>
          Synchro / ShellHacks 2026
          <span>Synthetic data · Provisional frontend contracts</span>
        </footer>
      </main>
    </>
  );
}
function MapSymbol() {
  return (
    <div className="study-icon">
      <Layers3 size={22} />
    </div>
  );
}
