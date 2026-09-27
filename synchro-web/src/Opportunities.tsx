import { useEffect, useState, type FormEvent } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { ArrowRight, ArrowUpRight, BadgeCheck, ChevronRight, Clock3, FileClock, FileDown, Layers3, LoaderCircle, LockKeyhole, MapPin, ShieldAlert } from 'lucide-react'
import { ApiError, exportAuditPdf, getLedger, getOpportunity, postDecision } from './api'
import MapPanel from './MapPanel'
import type { Ledger, Opportunity, QualifiedPairs } from './types'
import { safeSourceUrl } from './utils'

const actions = [
  { value: 'UNDER_REVIEW', label: 'Under review' },
  { value: 'NEEDS_MORE_DATA', label: 'Needs more data' },
  { value: 'APPROVE_COORDINATION', label: 'Approve coordination' },
  { value: 'PROPOSE_COORDINATED_PLAN', label: 'Propose coordinated plan' },
  { value: 'DISMISS', label: 'Dismiss' },
]

const eventLabels: Record<string, string> = {
  UNDER_REVIEW: 'Moved under review', NEEDS_MORE_DATA: 'Requested more data',
  APPROVE_COORDINATION: 'Coordination review approved', PROPOSE_COORDINATED_PLAN: 'Coordinated plan proposed',
  DISMISS: 'Opportunity dismissed', REASON_UPDATED: 'Reason updated',
  OPPORTUNITY_CREATED: 'Opportunity created', OPPORTUNITY_RECOMPUTED: 'Analysis recomputed',
  PROJECT_VERSION_CHANGED: 'Project version changed',
  AUDIT_EXPORTED: 'Immutable audit PDF exported',
}

function Evidence({ opportunity }: { opportunity: Opportunity }) {
  return <div className="opportunity-evidence">{opportunity.projects.map(project => <section className="evidence-group" key={project.project_id}>
    <div className="evidence-project"><span className="utility-avatar">{project.utility_id.slice(0, 1)}</span><div><strong>{project.project_name}</strong><small>{project.utility_id} · ASUS {project.version_id}{project.upstream_project_version_id ? ` · Mac ${project.upstream_project_version_id}` : ''}</small></div></div>
    <p className="muted-text">{project.location_text}</p>
    <div className="badge-row"><span className="badge neutral">{project.geometry_quality}</span><span className="badge neutral">{project.validation_state}</span></div>
    {project.evidence.map(source => {
      const href = safeSourceUrl(source.source_url)
      const content = <><span className="source-icon"><Layers3 size={16} /></span><span><strong>{source.source_name}</strong><small>{source.page_or_row ?? source.source_id}{source.snippet ? ` · ${source.snippet}` : ''}</small></span><ArrowUpRight size={15} /></>
      return href ? <a className="source-row" href={href} target="_blank" rel="noopener noreferrer" key={source.source_id}>{content}</a>
        : <div className="source-row" key={source.source_id}>{content}</div>
    })}
  </section>)}</div>
}

function LedgerView({ ledger, error }: { ledger: Ledger | null; error: string }) {
  if (error) return <div className="ledger-locked"><LockKeyhole size={25} /><strong>Decision Ledger is protected</strong><p>{error}</p></div>
  if (!ledger || ledger.events.length === 0) return <div className="empty-state"><FileClock size={31} /><strong>No decisions recorded</strong><span>Material actions will appear here with the analysis available at the time.</span></div>
  return <div className="ledger-list">{ledger.requires_re_review && <div className="notice caution"><ShieldAlert size={18} /> Project or analysis data changed after the latest manager decision. Review it again.</div>}
    {ledger.events.map(event => <article className="ledger-event" key={event.event_id}>
      <span className={`ledger-event-dot ${event.actor_id === 'system' ? 'system' : ''}`} />
      <div><div className="ledger-event-head"><strong>{eventLabels[event.event_type] ?? event.event_type.replaceAll('_', ' ')}</strong><time>{new Date(event.occurred_at).toLocaleString()}</time></div><small>{event.actor_role} · {event.actor_id}</small>
        {event.reason && <p className="ledger-reason">“{event.reason}”</p>}
        <div className="ledger-context">{event.snapshot?.distance?.meters !== undefined && <span>{(event.snapshot.distance.meters / 1000).toFixed(2)} km at decision</span>}<span>{event.snapshot?.distance?.engine_version ? `Engine ${event.snapshot.distance.engine_version}` : 'Snapshot retained'}</span></div>
      </div>
    </article>)}
  </div>
}

export default function Opportunities({ data, live, apiError, accessKey }: { data: QualifiedPairs; live: boolean; apiError: string; accessKey: string }) {
  const reduce = useReducedMotion()
  const [selectedId, setSelectedId] = useState('')
  const [detail, setDetail] = useState<Opportunity | null>(null)
  const [ledger, setLedger] = useState<Ledger | null>(null)
  const [ledgerError, setLedgerError] = useState('')
  const [tab, setTab] = useState<'overview' | 'evidence' | 'ledger'>('overview')
  const [action, setAction] = useState('UNDER_REVIEW')
  const [actor, setActor] = useState('')
  const [reason, setReason] = useState('')
  const [decisionError, setDecisionError] = useState('')
  const [decisionSuccess, setDecisionSuccess] = useState('')
  const [auditActor, setAuditActor] = useState('')
  const [auditBusy, setAuditBusy] = useState(false)
  const [auditError, setAuditError] = useState('')
  const [auditSuccess, setAuditSuccess] = useState<{ auditId: string; pdfHash: string } | null>(null)

  useEffect(() => {
    if (!data.opportunities.length) { setSelectedId(''); setDetail(null); return }
    if (!data.opportunities.some(pair => pair.pair_id === selectedId)) setSelectedId(data.opportunities[0].pair_id)
  }, [data, selectedId])

  useEffect(() => {
    if (!selectedId || !live) return
    let active = true
    setDetail(null); setLedger(null); setLedgerError('')
    getOpportunity(selectedId).then(value => { if (active) setDetail(value) }).catch(cause => { if (active) setDecisionError((cause as Error).message) })
    if (accessKey) getLedger(selectedId, accessKey).then(value => { if (active) setLedger(value) }).catch(cause => {
      if (active) setLedgerError((cause as ApiError).status === 401 ? 'Reviewer access expired or invalid. Connect the current API write key in the header.' : (cause as Error).message)
    })
    else setLedgerError('Connect reviewer access in the header to read the Decision Ledger.')
    return () => { active = false }
  }, [selectedId, live, accessKey])

  async function decide(event: FormEvent) {
    event.preventDefault()
    if (!detail?.decision_context_hash) return
    setDecisionError(''); setDecisionSuccess('')
    try {
      await postDecision(detail.pair_id, { action, actor_id: actor.trim(), actor_role: 'Regional Transmission Planning Manager',
        reason: reason.trim(), decision_context_hash: detail.decision_context_hash, idempotency_key: crypto.randomUUID() }, accessKey)
      setReason(''); setDecisionSuccess('Decision recorded with its analysis snapshot.')
      setLedger(await getLedger(detail.pair_id, accessKey))
    } catch (cause) {
      const error = cause as ApiError
      setDecisionError(error.status === 401 ? 'Reviewer key missing or invalid. Enter it under Reviewer access in the header.' : error.message)
      if (error.status === 409) getOpportunity(detail.pair_id).then(setDetail).catch(() => undefined)
    }
  }

  async function downloadAudit() {
    if (!detail || !auditActor.trim()) return
    setAuditBusy(true); setAuditError(''); setAuditSuccess(null)
    try {
      const result = await exportAuditPdf(detail.pair_id, auditActor.trim(), accessKey)
      const url = URL.createObjectURL(result.blob)
      const link = document.createElement('a')
      link.href = url; link.download = result.filename; document.body.appendChild(link); link.click(); link.remove()
      window.setTimeout(() => URL.revokeObjectURL(url), 1000)
      setAuditSuccess({ auditId: result.auditId, pdfHash: result.pdfSha256 })
      setLedger(await getLedger(detail.pair_id, accessKey))
    } catch (cause) {
      const error = cause as ApiError
      setAuditError(error.status === 401 ? 'Reviewer key missing or invalid. Enter it under Reviewer access in the header.' : error.message)
    } finally {
      setAuditBusy(false)
    }
  }

  if (!live) return <main className="workspace-page content-width">
    <div className="workspace-heading"><div><span className="eyebrow dark"><span className="eyebrow-line" /> REGIONAL PLANNING</span><h1>Coordination Opportunities</h1><p>Qualified opportunities require the current analysis API.</p></div></div>
    <div className="opportunity-empty"><LockKeyhole size={34} /><h2>Opportunity analysis unavailable</h2><p>{apiError || 'Waiting for the SYNCHRO API.'}</p><a className="button button-primary" href="#workbench">View current projects <ArrowRight size={17} /></a></div>
  </main>

  return <main className="workspace-page content-width">
    <div className="workspace-heading"><div><span className="eyebrow dark"><span className="eyebrow-line" /> REGIONAL PLANNING</span><h1>Coordination Opportunities</h1><p>Measured proximity becomes a manager decision only after the underlying projects are qualified.</p></div><span className="count-pill large">{data.total} qualified</span></div>
    {data.total === 0 ? <div className="opportunity-empty">
      <div className="empty-illustration"><div className="empty-ring ring-one" /><div className="empty-ring ring-two" /><MapPin size={31} /></div>
      <span className="eyebrow dark">NO QUALIFIED PAIR YET</span><h2>Good decisions start with<br /><em>real project locations.</em></h2>
      <p>No current DESC–Georgia Power pair meets the evidence, status, geometry, and distance gates. Verify source-backed sites in the Location Workbench; this page will update when a real opportunity qualifies.</p>
      <a className="button button-primary" href="#workbench">Review project locations <ArrowRight size={17} /></a>
      <div className="decision-preview"><span>DECISION PATH</span><div>{actions.map((item, index) => <div key={item.value}><span className="decision-step-number">0{index + 1}</span>{item.label}</div>)}</div><small>Available on a qualified opportunity. No decision has been recorded here.</small></div>
    </div> : <div className="opportunity-layout">
      <section className="panel opportunity-list"><div className="panel-head"><div><h2>Qualified pairs</h2><p>Strictly under {(data.maximum_meters / 1000).toFixed(1)} km.</p></div></div>{data.opportunities.map(pair => <button key={pair.pair_id} className={`opportunity-item ${selectedId === pair.pair_id ? 'selected' : ''}`} onClick={() => { setSelectedId(pair.pair_id); setTab('overview') }}><span className="opportunity-item-mark"><BadgeCheck size={19} /></span><span><strong>{pair.projects.map(project => project.project_name).join(' ↔ ')}</strong><small>{(pair.distance.meters / 1000).toFixed(2)} km · {pair.tier.replaceAll('_', ' ')}</small></span><ChevronRight size={17} /></button>)}</section>
      <section className="panel opportunity-detail">{detail ? <><div className="panel-head"><div><span className="detail-kicker">OPPORTUNITY / {detail.pair_id.slice(0, 12)}</span><h2>{detail.projects.map(project => project.project_name).join(' ↔ ')}</h2></div><span className="badge green">Qualified</span></div><div className="opportunity-summary"><div><span>DISTANCE</span><strong>{(detail.distance.meters / 1000).toFixed(2)} km</strong><small>{detail.distance.method.replaceAll('_', ' ')}</small></div><div><span>SPATIAL TIER</span><strong>{detail.tier.replaceAll('_', ' ')}</strong><small>{detail.distance.geometry_quality}</small></div><div><span>POTENTIAL IMPACT</span><strong>Not calculated</strong><small>Impact model pending</small></div></div>
        <div className="tabs" role="tablist" aria-label="Opportunity detail">{(['overview', 'evidence', 'ledger'] as const).map(value => <button key={value} role="tab" aria-selected={tab === value} className={tab === value ? 'active' : ''} onClick={() => setTab(value)}>{value === 'ledger' ? 'Decision Ledger' : value[0].toUpperCase() + value.slice(1)}</button>)}</div>
        <AnimatePresence mode="wait"><motion.div key={tab} initial={reduce ? undefined : { opacity: 0, y: 7 }} animate={{ opacity: 1, y: 0 }} exit={reduce ? undefined : { opacity: 0, y: -7 }} transition={{ duration: .18 }} className="tab-content">
          {tab === 'overview' && <><MapPanel projects={detail.projects} compact /><div className="opportunity-notes"><div><Clock3 size={18} /><strong>Timing relationship</strong><p>{String(detail.temporal_relationship.status ?? detail.temporal_relationship.type ?? 'Unknown').replaceAll('_', ' ')} · {detail.temporal_strength.replaceAll('_', ' ')}</p></div><div><Layers3 size={18} /><strong>Possible coordination areas</strong><p>{detail.possible_coordination_areas.join(', ')}</p></div></div><div className="notice neutral"><ShieldAlert size={17} /> Possible coordination areas are screening leads. Feasibility and economics require project-specific review.</div></>}
          {tab === 'evidence' && <Evidence opportunity={detail} />}
          {tab === 'ledger' && <><LedgerView ledger={ledger} error={ledgerError} /><section className="audit-export-card"><div className="audit-export-icon"><FileDown size={22} /></div><div className="audit-export-copy"><span className="detail-kicker">IMMUTABLE SNAPSHOT</span><h3>Export Audit PDF</h3><p>Save the projects, map evidence, source appendix, manager decision, and append-only trail exactly as reviewed.</p><label>Exporter / reviewer ID<input value={auditActor} onChange={event => setAuditActor(event.target.value)} placeholder="Authenticated user ID" /></label>{auditError && <div className="notice error" role="alert">{auditError}</div>}{auditSuccess && <div className="notice success" role="status"><strong>Audit {auditSuccess.auditId}</strong><span>PDF SHA-256: {auditSuccess.pdfHash || 'recorded in the ledger'}</span></div>}<button type="button" className="button button-secondary" onClick={downloadAudit} disabled={!accessKey || !auditActor.trim() || auditBusy}>{auditBusy ? <><LoaderCircle className="spin" size={17} /> Generating audit…</> : <>Export Audit PDF <FileDown size={17} /></>}</button>{!accessKey && <small>Connect reviewer access in the header before exporting.</small>}</div></section><form className="decision-form" onSubmit={decide}><h3>Record a manager decision</h3><p>Each action captures this analysis and both project versions.</p><div className="form-grid two"><label>Action<select value={action} onChange={e => setAction(e.target.value)}>{actions.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label><label>Manager ID<input required value={actor} onChange={e => setActor(e.target.value)} placeholder="Authenticated user ID" /></label></div><label>Reason<textarea required value={reason} onChange={e => setReason(e.target.value)} placeholder="State why this action is appropriate…" /></label><p className="form-footnote">Actor identity is client asserted until individual sign-in is connected.</p>{!accessKey && <div className="notice caution">Connect reviewer access in the header before recording a decision.</div>}{decisionError && <div className="notice error" role="alert">{decisionError}</div>}{decisionSuccess && <div className="notice success" role="status">{decisionSuccess}</div>}<button type="submit" className="button button-primary" disabled={!accessKey}>Record decision <ArrowRight size={17} /></button></form></>}
        </motion.div></AnimatePresence></> : <div className="empty-state"><Layers3 size={30} /><strong>Loading opportunity</strong><span>Fetching the current analysis snapshot.</span></div>}</section>
    </div>}
  </main>
}
