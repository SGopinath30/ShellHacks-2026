import type { Project } from "@/lib/types";
export default function SourceEvidence({ projects }: { projects: Project[] }) {
  return (
    <section className="evidence">
      <div className="section-title">
        <h3>Source evidence</h3>
        <span className="mini-badge">Synthetic</span>
      </div>
      <p className="muted">
        Illustrative evidence only. No source documents are available.
      </p>
      {projects.map((p) => (
        <div key={p.id}>
          <h4>{p.utilityName}</h4>
          {p.evidence.map((e) => (
            <details key={e.field}>
              <summary>
                {e.field}
                <span>＋</span>
              </summary>
              <p>“{e.quote}”</p>
              <small>
                {e.sourceTitle} · {e.pageOrRow}
                <br />
                Source unavailable · synthetic record
              </small>
            </details>
          ))}
        </div>
      ))}
    </section>
  );
}
