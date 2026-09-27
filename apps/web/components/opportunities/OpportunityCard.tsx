import { ArrowUpRight, MapPin, CalendarDays } from "lucide-react";
import type { Match, Project } from "@/lib/types";
import { assessMatch, distanceMiles, utilityColor } from "@/lib/utils";
export default function OpportunityCard({
  match,
  projects,
  selected,
  onSelect,
}: {
  match: Match;
  projects: Project[];
  selected: boolean;
  onSelect: () => void;
}) {
  const { pair, status, overlap } = assessMatch(match, projects);
  if (!pair)
    return (
      <button
        className="opportunity"
        aria-pressed={selected}
        onClick={onSelect}
      >
        Project data unavailable — referenced project missing
      </button>
    );
  const distance = distanceMiles(...pair);
  return (
    <button
      className={`opportunity ${selected ? "selected" : ""}`}
      aria-pressed={selected}
      onClick={onSelect}
    >
      <span className="card-top">
        <span>
          {status === "invalid"
            ? "Invalid schedule — review required"
            : status === "incomplete"
              ? "SCHEDULE NEEDED"
              : status === "overlap"
                ? "COORDINATION OPPORTUNITY"
                : "NO COORDINATION OPPORTUNITY"}
        </span>
        <ArrowUpRight size={15} />
      </span>
      {pair.map((p) => (
        <span className="card-project" key={p.id}>
          <i style={{ background: utilityColor(p.utilityId) }} />
          <span>
            <strong>{p.name}</strong>
            <small>{p.utilityName}</small>
          </span>
        </span>
      ))}
      <span className="card-metrics">
        <span>
          <MapPin size={13} />
          {distance === null
            ? "Location unavailable"
            : `${distance.toFixed(2)} mi`}
        </span>
        <span>
          <CalendarDays size={13} />
          {overlap === null
            ? status === "invalid"
              ? "Invalid schedule — review required"
              : "Timing unknown"
            : `${overlap} days overlap`}
        </span>
      </span>
    </button>
  );
}
