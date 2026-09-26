import type { Match, Project } from "@/lib/types";
import { assessMatch, formatDate, utilityColor } from "@/lib/utils";
import ConstructionScheduleText from "../timeline/ConstructionScheduleText";
import SourceEvidence from "../evidence/SourceEvidence";
export default function MatchDetails({
  match,
  projects,
}: {
  match: Match | null;
  projects: Project[];
}) {
  if (!match)
    return (
      <aside className="details panel">
        <h2>Pair details</h2>
        <p className="muted">
          Adjust your filters and select a pair to inspect its projects and
          evidence.
        </p>
      </aside>
    );
  const { pair, status, overlap } = assessMatch(match, projects);
  if (!pair)
    return (
      <aside className="details panel">
        <h2>Project data unavailable</h2>
        <p>A referenced project is missing. This pair cannot be compared.</p>
      </aside>
    );
  return (
    <aside className="details panel">
      <div className="eyebrow">PAIR INSIGHTS</div>
      <h2>
        {status === "invalid"
          ? "Invalid schedule — review required"
          : status === "overlap"
            ? "A window to work together"
            : status === "incomplete"
              ? "Schedule to be confirmed"
              : "No coordination opportunity"}
      </h2>
      <p className="muted">
        {status === "overlap"
          ? "Nearby projects from different utilities share a construction window."
          : "This pair does not establish a confirmed opportunity. Review construction schedules and utility information."}
      </p>
      <div className="detail-metrics">
        <div>
          <strong>
            {match.distanceMiles.toFixed(2)}
            <small> mi</small>
          </strong>
          <span>Point distance</span>
        </div>
        <div>
          <strong>
            {overlap ?? "—"}
            <small>{overlap !== null && " days"}</small>
          </strong>
          <span>Construction overlap</span>
        </div>
      </div>
      <h3>Selected projects</h3>
      {pair.map((p) => (
        <article className="project-detail" key={p.id}>
          <div
            className="utility-label"
            style={{ color: utilityColor(p.utilityId) }}
          >
            ● {p.utilityName}
            <span>{p.id}</span>
          </div>
          <h4>{p.name}</h4>
          <p>
            {p.type} · {p.status}
          </p>
          <dl>
            <dt>Construction</dt>
            <dd>
              <ConstructionScheduleText project={p} />
            </dd>
            <dt>In service milestone</dt>
            <dd>
              {p.inServiceDate ? formatDate(p.inServiceDate) : "Not provided"}
            </dd>
            <dt>Location / dates</dt>
            <dd>Approximate point / {p.datePrecision}</dd>
          </dl>
        </article>
      ))}
      <SourceEvidence projects={pair} />
      <p className="footnote">
        All utilities, projects, and evidence are fictional. Proximity does not
        verify a shared corridor or feasibility.
      </p>
    </aside>
  );
}
