"use client";
import type { Project } from "@/lib/types";
import { useUtilityColor } from "../UtilityColors";
import {
  constructionSchedule,
  formatDate,
  overlapDays,
  parseCalendarDate,
  projectDateStatus,
} from "@/lib/utils";
import OverlapHighlight from "./OverlapHighlight";
import ConstructionScheduleText from "./ConstructionScheduleText";
export default function ProjectTimeline({
  projects,
  selectedDate,
  dateRange,
  onDateChange,
}: {
  projects: Project[] | null;
  selectedDate?: string | null;
  dateRange?: { min: string | null; max: string | null };
  onDateChange?: (value: string) => void;
}) {
  const utilityColor = useUtilityColor();
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
  const min =
    parseCalendarDate(dateRange?.min ?? null) ??
    (windows.length ? Math.min(...windows.map((s) => s.start)) : null);
  const max =
    parseCalendarDate(dateRange?.max ?? null) ??
    (windows.length ? Math.max(...windows.map((s) => s.end)) : null);
  const timelineMin =
    dateRange?.min ??
    (min !== null ? new Date(min).toISOString().slice(0, 10) : null);
  const timelineMax =
    dateRange?.max ??
    (max !== null ? new Date(max).toISOString().slice(0, 10) : null);
  const effectiveDate = selectedDate ?? timelineMin ?? "2027-01-01";
  const scale = (date: number) =>
    min !== null && max !== null && max > min
      ? Math.max(0, Math.min(100, ((date - min) / (max - min)) * 100))
      : 0;
  const overlap = pair.length === 2 ? overlapDays(pair[0], pair[1]) : null;
  const invalid = rows.some((row) => row.schedule.status === "invalid");
  return (
    <section className="timeline panel" id="construction-timeline">
      <div className="section-title">
        <div>
          <div className="eyebrow">CONSTRUCTION SCHEDULE</div>
          <h2>Move the date. See what’s active.</h2>
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
      {timelineMin && timelineMax && onDateChange && (
        <div className="date-focus">
          <label htmlFor="timeline-date-focus">Selected date</label>
          <div className="date-focus-input-row">
            <input
              id="timeline-date-focus"
              type="date"
              min={timelineMin}
              max={timelineMax}
              value={effectiveDate}
              onChange={(event) => onDateChange(event.target.value)}
            />
            <strong>{formatDate(effectiveDate)}</strong>
          </div>
          <div className="date-focus-meta">
            <span>{formatDate(timelineMin)}</span>
            <span>{formatDate(timelineMax)}</span>
          </div>
          <input
            className="year-slider"
            type="range"
            aria-label="Explore construction date"
            aria-valuetext={formatDate(effectiveDate)}
            min={parseCalendarDate(timelineMin)!}
            max={parseCalendarDate(timelineMax)!}
            step={86400000}
            value={
              parseCalendarDate(effectiveDate) ??
              parseCalendarDate(timelineMin)!
            }
            onChange={(e) =>
              onDateChange(
                new Date(Number(e.target.value)).toISOString().slice(0, 10),
              )
            }
          />
          <div className="year-ticks" aria-hidden="true">
            {Array.from(
              {
                length:
                  new Date(timelineMax).getUTCFullYear() -
                  new Date(timelineMin).getUTCFullYear() +
                  1,
              },
              (_, i) => (
                <span key={i}>
                  {new Date(timelineMin).getUTCFullYear() + i}
                </span>
              ),
            )}
          </div>
        </div>
      )}
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
            <div
              className={`timeline-row ${projectDateStatus(p, selectedDate ?? null) === "active" ? "timeline-active" : ""}`}
              key={p.id}
            >
              <span>
                <i style={{ background: utilityColor(p.utilityId) }} />
                {p.utilityName}
                {selectedDate && (
                  <small className="timeline-status">
                    {projectDateStatus(p, selectedDate)}
                  </small>
                )}
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
                  {selectedDate && parseCalendarDate(selectedDate) !== null && (
                    <div
                      className="timeline-cursor"
                      style={{
                        left: `${scale(parseCalendarDate(selectedDate)!)}%`,
                      }}
                    />
                  )}
                </div>
              ) : (
                <div className="unknown-timing">
                  <ConstructionScheduleText project={p} />
                  {p.scheduleNote && (
                    <small className="block">{p.scheduleNote}</small>
                  )}
                  {p.inServiceDate && (
                    <small className="block">
                      In-service milestone: {formatDate(p.inServiceDate)}.
                      Construction window not supplied.
                    </small>
                  )}
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
