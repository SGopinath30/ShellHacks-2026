import type { Project } from "@/lib/types";
import { constructionSchedule, formatDate } from "@/lib/utils";
export default function ConstructionScheduleText({
  project,
}: {
  project: Project;
}) {
  const schedule = constructionSchedule(project);
  if (schedule.status === "valid")
    return (
      <>
        {formatDate(project.constructionStart)} –{" "}
        {formatDate(project.constructionEnd)}
      </>
    );
  if (schedule.status === "invalid")
    return (
      <>
        <span>Invalid construction schedule</span>
        <br />
        <small>Dates require review.</small>
        <br />
        <small>
          Supplied construction start:{" "}
          {project.constructionStart ?? "Not provided"}
        </small>
        <br />
        <small>
          Supplied construction end: {project.constructionEnd ?? "Not provided"}
        </small>
      </>
    );
  return (
    <>
      <span>Timing unknown</span>
      <br />
      {schedule.start === null && schedule.end === null ? (
        <small>Construction dates not provided</small>
      ) : (
        <>
          <small>
            {schedule.start !== null
              ? `Known construction start: ${formatDate(project.constructionStart)}`
              : "Construction start: Not provided"}
          </small>
          <br />
          <small>
            {schedule.end !== null
              ? `Known construction end: ${formatDate(project.constructionEnd)}`
              : "Construction end: Not provided"}
          </small>
        </>
      )}
    </>
  );
}
