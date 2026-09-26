import type { Match, Project } from "@/lib/types";
import OpportunityCard from "./OpportunityCard";
export default function OpportunityList({
  matches,
  projects,
  selectedId,
  onSelect,
}: {
  matches: Match[];
  projects: Project[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <div className="opportunity-list">
      {matches.map((match) => (
        <OpportunityCard
          key={match.id}
          match={match}
          projects={projects}
          selected={match.id === selectedId}
          onSelect={() => onSelect(match.id)}
        />
      ))}
    </div>
  );
}
