"use client";
import { motion, useReducedMotion } from "motion/react";
import type { CoordinationMatch, Project } from "@/lib/types";
import { resolvePair } from "@/lib/utils";
import { relationshipPhase, timingLabel } from "@/lib/coordination";
import { useUtilityColor } from "../UtilityColors";

export default function CoordinationCard({
  match,
  projects,
  selected,
  selectedDate,
  rank,
  onSelect,
}: {
  match: CoordinationMatch;
  projects: Project[];
  selected: boolean;
  selectedDate: string | null;
  rank?: number;
  onSelect: () => void;
}) {
  const color = useUtilityColor();
  const reduceMotion = useReducedMotion();
  const pair = resolvePair(match, projects);
  if (!pair) return null;
  const phase = relationshipPhase(match, selectedDate);
  return (
    <motion.button
      initial={reduceMotion ? false : { opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        duration: reduceMotion ? 0 : 0.18,
        delay: reduceMotion ? 0 : Math.min((rank ?? 1) - 1, 3) * 0.025,
        ease: "easeOut",
      }}
      whileHover={reduceMotion ? undefined : { y: -1 }}
      whileTap={reduceMotion ? undefined : { y: 0 }}
      className={`opportunity ${selected ? "selected" : ""}`}
      aria-pressed={selected}
      onClick={onSelect}
    >
      <span className="card-top">
        <strong>{rank ? `#${rank}` : "REVIEW"}</strong>
        <span>
          {match.source === "api"
            ? `TIER: ${match.tier}`
            : phase === "active"
              ? "COLLISION / SYNERGY ALERT"
              : match.eligible
                ? `${phase.toUpperCase()} OPPORTUNITY`
                : "SCHEDULE NEEDED"}
        </span>
      </span>
      {pair.map((project, index) => (
        <span className="card-project" key={project.id}>
          <i style={{ background: color(project.utilityId) }} />
          <span>
            <strong>{project.name}</strong>
            <small>
              {index === 0 ? "↔ " : ""}
              {project.utilityName}
            </small>
          </span>
        </span>
      ))}
      <span className="card-metrics">
        <span>{match.distanceMiles.toFixed(2)} mi apart</span>
        <span>{timingLabel(match)}</span>
      </span>
      <span className="coordination-category">
        Explore shared access or staging
      </span>
    </motion.button>
  );
}
