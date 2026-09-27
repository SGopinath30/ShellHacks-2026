import type { Project } from "@/lib/types";
import { safeSourceUrl } from "@/lib/utils";
export default function SourceEvidence({ projects }: { projects: Project[] }) {
  const entries = projects.flatMap((project) =>
    project.evidence.map((evidence, index) => ({ project, evidence, index })),
  );
  const allSynthetic =
    entries.length > 0 &&
    entries.every(({ evidence }) => evidence.synthetic === true);
  return (
    <section className="evidence">
      <div className="section-title">
        <h3>Source evidence</h3>
        {allSynthetic && <span className="mini-badge">Synthetic</span>}
      </div>
      {entries.length === 0 ? (
        <p className="muted">No source evidence provided.</p>
      ) : (
        <>
          {allSynthetic && (
            <p className="muted">
              Illustrative evidence from synthetic records.
            </p>
          )}
          {projects.map((project) => (
            <div key={project.id}>
              <h4>
                {project.utilityName}
                {project.synthetic && (
                  <span className="mini-badge"> Synthetic</span>
                )}
              </h4>
              {project.evidence.map((evidence, index) => {
                const url = safeSourceUrl(evidence.sourceUrl);
                return (
                  <details key={`${project.id}-${index}`}>
                    <summary>
                      {evidence.field}
                      <span>＋</span>
                    </summary>
                    {evidence.synthetic && (
                      <small>
                        Synthetic evidence
                        <br />
                      </small>
                    )}
                    <p>“{evidence.quote}”</p>
                    <small>
                      {evidence.sourceTitle}
                      {evidence.pageOrRow ? ` · ${evidence.pageOrRow}` : ""}
                      <br />
                      {url ? (
                        <a href={url} target="_blank" rel="noopener noreferrer">
                          Open source
                        </a>
                      ) : (
                        "Source link unavailable."
                      )}
                    </small>
                  </details>
                );
              })}
            </div>
          ))}
        </>
      )}
    </section>
  );
}
