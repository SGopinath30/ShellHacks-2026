import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { mkdirSync, writeFileSync } from "node:fs";
import { completeA, completeB, scheduleCases } from "../lib/schedule-cases";
import { buildMatches } from "../lib/utils";
import MatchDetails from "../components/opportunities/MatchDetails";
import OpportunityCard from "../components/opportunities/OpportunityCard";
import ProjectTimeline from "../components/timeline/ProjectTimeline";
const markup: Record<string, string> = {};
for (const item of scheduleCases) {
  const projects = [completeA, item.project];
  const match = { ...buildMatches(projects)[0], overlapDays: 999 };
  markup[item.name] = renderToStaticMarkup(
    <>
      <MatchDetails match={match} projects={projects} />
      <OpportunityCard
        match={match}
        projects={projects}
        selected
        onSelect={() => {}}
      />
      <ProjectTimeline projects={projects} />
    </>,
  );
}
markup.empty = renderToStaticMarkup(
  <>
    <MatchDetails match={null} projects={[]} />
    <ProjectTimeline projects={[]} />
  </>,
);
markup.missing = renderToStaticMarkup(
  <>
    <MatchDetails
      match={buildMatches([completeA, completeB])[0]}
      projects={[completeA]}
    />
    <OpportunityCard
      match={buildMatches([completeA, completeB])[0]}
      projects={[completeA]}
      selected
      onSelect={() => {}}
    />
    <ProjectTimeline projects={null} />
  </>,
);
markup["no-valid-windows"] = renderToStaticMarkup(
  <ProjectTimeline
    projects={[
      scheduleCases[3].project,
      { ...scheduleCases[9].project, id: "other" },
    ]}
  />,
);
mkdirSync(".test-fixtures", { recursive: true });
writeFileSync(".test-fixtures/schedules.json", JSON.stringify(markup));
