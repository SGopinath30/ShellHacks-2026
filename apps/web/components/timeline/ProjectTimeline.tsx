import type { Project } from "@/lib/types";
import {
  constructionSchedule,
  formatDate,
  overlapDays,
  utilityColor,
} from "@/lib/utils";
import OverlapHighlight from "./OverlapHighlight";
import ConstructionScheduleText from "./ConstructionScheduleText";
export default function ProjectTimeline({
  projects,
}: {
  projects: Project[] | null;
}) {
  const unavailable =
    projects === null || (projects.length !== 0 && projects.length !== 2);
  const pair = unavailable ? [] : projects;
  const rows = pair.map((project) => ({
    project,
    schedule: constructionSchedule(project),
  }));
  const windows = rows
    .map((row) => row.schedule)
    .filter((s) => s.status === "valid");
  const min = windows.length ? Math.min(...windows.map((s) => s.start)) : null;
  const max = windows.length ? Math.max(...windows.map((s) => s.end)) : null;
  const scale = (date: number) =>
    min !== null && max !== null && max > min
      ? Math.max(0, Math.min(100, ((date - min) / (max - min)) * 100))
      : 0;
  const overlap = pair.length === 2 ? overlapDays(pair[0], pair[1]) : null;
  const invalid = rows.some((row) => row.schedule.status === "invalid");
  return (
    <section className="timeline panel">
      <div className="section-title">
        <div>
          <div className="eyebrow">CONSTRUCTION SCHEDULE</div>
          <h2>Timing is everything.</h2>
        </div>
        {pair.length === 2 && (
          <span className="mini-badge">
            {invalid
              ? "Invalid schedule"
              : overlap === null
                ? "Timing unknown"
                : overlap + " shared days"}
          </span>
        )}
      </div>
      {unavailable ? (
        <p className="muted">
          Project data unavailable: both referenced projects are required for
          comparison.
        </p>
      ) : pair.length === 0 ? (
        <p className="muted">Select a pair to compare construction windows.</p>
      ) : (
        <>
          {min !== null && max !== null && (
            <div className="timeline-scale">
              <span>
                {formatDate(new Date(min).toISOString().slice(0, 10))}
              </span>
              <span>
                {formatDate(new Date(max).toISOString().slice(0, 10))}
              </span>
            </div>
          )}
          {rows.map(({ project: p, schedule }) => (
            <div className="timeline-row" key={p.id}>
              <span>
                <i style={{ background: utilityColor(p.utilityId) }} />
                {p.utilityName}
              </span>
              {schedule.status === "valid" ? (
                <div className="timeline-track">
                  <div
                    className="timeline-bar"
                    title={
                      formatDate(p.constructionStart) +
                      " to " +
                      formatDate(p.constructionEnd)
                    }
                    style={{
                      background: utilityColor(p.utilityId),
                      left: scale(schedule.start) + "%",
                      width:
                        Math.max(
                          0,
                          scale(schedule.end) - scale(schedule.start),
                        ) + "%",
                    }}
                  />
                  {overlap !== null && overlap > 0 && windows.length === 2 && (
                    <OverlapHighlight
                      left={scale(Math.max(...windows.map((s) => s.start)))}
                      width={
                        scale(Math.min(...windows.map((s) => s.end))) -
                        scale(Math.max(...windows.map((s) => s.start)))
                      }
                    />
                  )}
                </div>
              ) : (
                <div className="unknown-timing">
                  <ConstructionScheduleText project={p} />
                </div>
              )}
            </div>
          ))}
          <p className="footnote">
            Hatched area: actual overlap · Start inclusive, end exclusive ·
            In-service milestones are not construction windows.
          </p>
        </>
      )}
    </section>
  );
}
