"use client";
import { motion, useReducedMotion } from "motion/react";
import type { CoordinationMatch, Project } from "@/lib/types";
import {
  formatDate,
  projectDateStatus,
  resolvePair,
  safeSourceUrl,
} from "@/lib/utils";
import { timingLabel } from "@/lib/coordination";
import { useUtilityColor, COMPARISON_COLORS } from "../UtilityColors";
import ConstructionScheduleText from "../timeline/ConstructionScheduleText";

export default function CoProcurementDossier({
  match,
  projects,
  selectedDate,
  onClose,
}: {
  match: CoordinationMatch;
  projects: Project[];
  selectedDate: string | null;
  onClose: () => void;
}) {
  const color = useUtilityColor();
  const reduceMotion = useReducedMotion();
  const pair = resolvePair(match, projects);
  if (!pair) return null;
  return (
    <motion.section
      initial={reduceMotion ? false : { opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: reduceMotion ? 0 : 0.2, ease: "easeOut" }}
      className="panel dossier"
      id="dossier"
      tabIndex={-1}
      aria-labelledby="dossier-title"
    >
      <div className="section-title">
        <div>
          <div className="eyebrow">EXPLORE A COORDINATED APPROACH</div>
          <h2 id="dossier-title">Co-Procurement Dossier</h2>
        </div>
        <button className="text-button" onClick={onClose}>
          Close dossier
        </button>
      </div>
      <p className="muted">
        {pair[0].name} ↔ {pair[1].name}
      </p>
      <div className="dossier-columns">
        <div>
          <h3>Source evidence</h3>
          <p className="muted small">
            {pair.some((p) => p.synthetic)
              ? "Synthetic demo records — no source filings are represented."
              : "Review the stored source records below."}
          </p>
          {[...pair]
            .sort((a) => (color(a.utilityId) === COMPARISON_COLORS[0] ? -1 : 1))
            .map((p) => (
              <article
                className="evidence-project"
                style={{ borderColor: color(p.utilityId) }}
                key={p.id}
              >
                <div
                  className="utility-label"
                  style={{ color: color(p.utilityId) }}
                >
                  Utility{" "}
                  {color(p.utilityId) === COMPARISON_COLORS[0] ? "A" : "B"} ·{" "}
                  {p.utilityName}
                </div>
                <h4>{p.name}</h4>
                <p>{p.type}</p>
                <dl>
                  <dt>Construction</dt>
                  <dd>
                    <ConstructionScheduleText project={p} />
                    {p.scheduleNote && <p>{p.scheduleNote}</p>}
                  </dd>
                  {p.inServiceDate && (
                    <>
                      <dt>In-service milestone</dt>
                      <dd>
                        {formatDate(p.inServiceDate)} (not a construction
                        window)
                      </dd>
                    </>
                  )}
                  {p.validationState && (
                    <>
                      <dt>Validation</dt>
                      <dd>{p.validationState}</dd>
                      <dt>Geometry quality</dt>
                      <dd>{p.geometryQuality}</dd>
                    </>
                  )}
                  <dt>At selected date</dt>
                  <dd>{projectDateStatus(p, selectedDate)}</dd>
                </dl>
                {!p.evidence.length && <p>No source evidence provided.</p>}
                {p.evidence.map((e, i) => {
                  const url = safeSourceUrl(e.sourceUrl);
                  return (
                    <details
                      className="dossier-evidence"
                      key={i}
                      open={i === 0}
                    >
                      <summary>
                        {e.field}{" "}
                        {e.synthetic && (
                          <span className="mini-badge">Synthetic</span>
                        )}
                        <span className="citation">
                          {e.sourceTitle} ·{" "}
                          {e.pageOrRow ?? "Page / row not provided"}
                        </span>
                      </summary>
                      <blockquote>{e.quote}</blockquote>
                      {url ? (
                        <a
                          className="text-button"
                          href={url}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          Open source ↗
                        </a>
                      ) : (
                        <small className="muted">
                          Source link unavailable.
                        </small>
                      )}
                    </details>
                  );
                })}
              </article>
            ))}
        </div>
        <div className="planning-column">
          <h3>Joint RFP / Shared Resource Brief</h3>
          <div className="brief-state">
            <strong>AI-assisted planning brief unavailable</strong>
            <p>Nemotron has not supplied a brief for these records.</p>
          </div>
          <h4>
            {match.source === "api"
              ? "Reported by the API"
              : "Measured from the demo records"}
          </h4>
          <div className="dossier-facts">
            <strong>{match.distanceMiles.toFixed(2)} mi apart</strong>
            <span>{timingLabel(match)}</span>
            <small>
              {match.source === "api"
                ? "Distance and tier are provided by the service. Map links identify pairs, not measured routes."
                : "Approximate project points; corridor distance is unavailable."}
            </small>
          </div>
          <h4>Questions to explore</h4>
          <p className="muted small">
            Planning checklist, not AI-generated recommendations.
          </p>
          <div className="brief-item">
            <strong>Potential shared labor</strong>
            <p>
              No labor requirements are recorded. Confirm scopes and crew needs
              with both utilities.
            </p>
          </div>
          <div className="brief-item">
            <strong>Potential shared equipment</strong>
            <p>
              No compatible equipment requirements are documented. Request
              specifications before exploring a joint RFP.
            </p>
          </div>
          <div className="brief-item">
            <strong>Procurement timing</strong>
            <p>
              {match.eligible && match.focusWindow
                ? `Review coordination around ${formatDate(match.focusWindow.start)}–${formatDate(match.focusWindow.end)}. Procurement dates and lead times are not provided.`
                : "Confirm both construction schedules before assessing procurement timing."}
            </p>
          </div>
          <div className="brief-item">
            <strong>Mobilization / logistics</strong>
            <p>
              {match.eligible
                ? "Explore whether access or staging could be shared. Land rights, route geometry, and mobilization plans need confirmation."
                : "A qualifying relationship has not been established. Resolve the missing information first."}
            </p>
          </div>
          <div className="impact-state">
            <h4>Impact estimate</h4>
            <p>Not enough source data to estimate defensibly.</p>
          </div>
          <p className="footnote">
            Evidence / assumptions: geographic proximity and construction timing
            do not establish compatible equipment, shared land, cost savings, or
            procurement feasibility.
          </p>
        </div>
      </div>
    </motion.section>
  );
}
