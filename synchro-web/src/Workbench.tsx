import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { ArrowRight, ArrowUpRight, CheckCircle2, Database, FileSearch, MapPin, RefreshCw, ShieldAlert, X } from 'lucide-react'
import { ApiError, getAssessment, postVerification } from './api'
import MapPanel from './MapPanel'
import type { PairAssessment, Project, ReviewQueue } from './types'
import { safeSourceUrl } from './utils'

const blockerNames: Record<string, string> = {
  FIXTURE: 'Starter fixture', MISSING_GEOMETRY: 'Missing geometry', UNRESOLVED_GEOMETRY: 'Location unresolved',
  APPROXIMATE_GEOMETRY: 'Approximate geometry', REFERENCE_CENTER_POINT: 'Reference point',
  VALIDATION_PENDING: 'Validation pending', STATUS_NOT_ELIGIBLE: 'Status needs confirmation',
  PROJECT_A_NEEDS_REVIEW: 'First record needs review', PROJECT_B_NEEDS_REVIEW: 'Second record needs review',
  OUT_OF_RANGE: 'Outside the distance threshold', SAME_UTILITY: 'Same utility', SAME_PROJECT: 'Same project',
}

type Props = { projects: Project[]; queue: ReviewQueue; maximumMeters: number; live: boolean; projectsLoaded: boolean; apiError: string; loading: boolean; onReload: () => Promise<void>; accessKey: string }

function SourceList({ project }: { project: Project }) {
  return <div className="source-list">
    {project.evidence.map(source => {
      const href = safeSourceUrl(source.source_url)
      const content = <>
      <span className="source-icon"><FileSearch size={17} /></span>
      <span><strong>{source.source_name}</strong><small>{source.page_or_row || source.source_id}{source.snippet ? ` · ${source.snippet}` : ''}</small></span>
      <ArrowUpRight size={15} />
      </>
      return href ? <a key={source.source_id} className="source-row" href={href} target="_blank" rel="noopener noreferrer">{content}</a>
        : <div key={source.source_id} className="source-row">{content}</div>
    })}
  </div>
}

function VerificationPanel({ project, live, accessKey, onClose, onSaved }: { project: Project; live: boolean; accessKey: string; onClose: () => void; onSaved: () => Promise<void> }) {
  const [form, setForm] = useState({ actor: '', reason: '', location: '', lon: '', lat: '', origin: 'UTILITY_GIS', quality: 'HIGH',
    sourceId: '', sourceName: '', sourceUrl: '', sourceRow: '', status: '', statusId: '', statusName: '', statusUrl: '', statusSnippet: '' })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const set = (key: keyof typeof form, value: string) => setForm(previous => ({ ...previous, [key]: value }))
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!live) return
    setSaving(true); setError('')
    try {
      const statusChanged = form.status && form.status !== project.status
      const result = await postVerification(project.project_id, {
        base_version_id: project.version_id, actor_id: form.actor.trim(), actor_role: 'Location Reviewer',
        reason: form.reason.trim(), location_text: form.location.trim(),
        geometry: { type: 'Point', coordinates: [Number(form.lon), Number(form.lat)] },
        geometry_origin: form.origin, geometry_quality: form.quality,
        geometry_evidence: { source_id: form.sourceId.trim(), source_name: form.sourceName.trim(),
          source_url: form.sourceUrl.trim(), page_or_row: form.sourceRow.trim() },
        ...(statusChanged ? { status: form.status, status_evidence: { source_id: form.statusId.trim(),
          source_name: form.statusName.trim(), source_url: form.statusUrl.trim(), snippet: form.statusSnippet.trim() } } : {}),
      }, accessKey)
      if (result.project.version_id) { await onSaved(); onClose() }
    } catch (cause) {
      const apiError = cause as ApiError
      setError(apiError.status === 401 ? 'Reviewer key missing or invalid. Enter it under Reviewer access in the header.' : apiError.message)
    } finally { setSaving(false) }
  }
  const statusChanged = form.status !== '' && form.status !== project.status
  return <motion.div className="drawer-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}>
    <motion.aside className="verification-drawer" role="dialog" aria-modal="true" aria-label={`Verify ${project.project_name}`}
      initial={{ x: 520 }} animate={{ x: 0 }} exit={{ x: 520 }} transition={{ type: 'spring', stiffness: 350, damping: 34 }} onClick={event => event.stopPropagation()}>
      <div className="drawer-head"><span className="eyebrow dark">SOURCE REVIEW</span><button className="icon-button" onClick={onClose} aria-label="Close verification"><X size={20} /></button></div>
      <h2>Verify location</h2><p className="drawer-intro">{project.project_name}</p>
      <div className="notice caution"><ShieldAlert size={18} /><span>Confirm project-specific geometry in a filing map or GIS feature. The current reference point does not locate the project site.</span></div>
      <form className="verify-form" onSubmit={submit}>
        <div className="form-grid two"><label>Reviewer ID<input required value={form.actor} onChange={e => set('actor', e.target.value)} placeholder="Your reviewer ID" /></label><label>Base version<input value={project.version_id} readOnly /></label></div>
        <label>Reason for correction<textarea required value={form.reason} onChange={e => set('reason', e.target.value)} placeholder="How did you identify this site?" /></label>
        <label>Verified location description<input required value={form.location} onChange={e => set('location', e.target.value)} placeholder="Project site and locality supported by the source" /></label>
        <div className="form-grid two"><label>Longitude<input required type="number" min="-180" max="180" step="any" value={form.lon} onChange={e => set('lon', e.target.value)} placeholder="-81.000000" /></label><label>Latitude<input required type="number" min="-90" max="90" step="any" value={form.lat} onChange={e => set('lat', e.target.value)} placeholder="32.000000" /></label></div>
        <div className="form-grid two"><label>Geometry origin<select value={form.origin} onChange={e => set('origin', e.target.value)}><option>UTILITY_GIS</option><option>PUBLIC_GIS</option><option>OSM_MATCH</option><option>SINGLE_LOCATED_POINT</option><option>MANUAL_VERIFIED</option></select></label><label>Quality<select value={form.quality} onChange={e => set('quality', e.target.value)}><option>HIGH</option><option>AUTHORITATIVE</option><option>APPROXIMATE</option></select></label></div>
        <div className="form-divider">GEOMETRY EVIDENCE</div>
        <div className="form-grid two"><label>Source ID<input required value={form.sourceId} onChange={e => set('sourceId', e.target.value)} /></label><label>Source name<input required value={form.sourceName} onChange={e => set('sourceName', e.target.value)} /></label></div>
        <label>Source URL<input required type="url" value={form.sourceUrl} onChange={e => set('sourceUrl', e.target.value)} placeholder="https://…" /></label>
        <label>Page, row, or feature ID<input required value={form.sourceRow} onChange={e => set('sourceRow', e.target.value)} placeholder="Exhibit B / GIS feature 42" /></label>
        <div className="form-divider">STATUS REVIEW</div>
        <label>Current status<select value={form.status} onChange={e => set('status', e.target.value)}><option value="">Keep {project.status}</option>{['proposed', 'planned', 'approved', 'in_progress', 'under_construction', 'on_hold', 'cancelled', 'unknown'].filter(value => value !== project.status).map(value => <option key={value} value={value}>{value.replaceAll('_', ' ')}</option>)}</select></label>
        {statusChanged && <div className="form-grid"><label>Status source ID<input required value={form.statusId} onChange={e => set('statusId', e.target.value)} /></label><label>Status source name<input required value={form.statusName} onChange={e => set('statusName', e.target.value)} /></label><label>Status source URL<input required type="url" value={form.statusUrl} onChange={e => set('statusUrl', e.target.value)} /></label><label>Supporting snippet<input required value={form.statusSnippet} onChange={e => set('statusSnippet', e.target.value)} /></label></div>}
        <p className="form-footnote">A high or authoritative geometry becomes accepted. Approximate geometry remains in review. Protected deployments require the reviewer key in the header. Reviewer identity is client asserted.</p>
        {error && <div className="notice error" role="alert">{error}</div>}
        <button className="button button-primary full" type="submit" disabled={!live || saving}>{saving ? 'Saving project version…' : live ? 'Save reviewed version' : 'Connect API to save'}</button>
      </form>
    </motion.aside>
  </motion.div>
}

export default function Workbench({ projects, queue, maximumMeters, live, projectsLoaded, apiError, loading, onReload, accessKey }: Props) {
  const reduce = useReducedMotion()
  const [selectedId, setSelectedId] = useState('')
  const [a, setA] = useState('')
  const [b, setB] = useState('')
  const [assessment, setAssessment] = useState<PairAssessment | null>(null)
  const [assessmentError, setAssessmentError] = useState('')
  const [verify, setVerify] = useState(false)
  const selected = useMemo(() => projects.find(project => project.project_id === selectedId) ?? queue.projects[0]?.project ?? projects.find(project => !project.is_fixture), [projects, queue, selectedId])
  const visibleRows = live ? queue.projects : projects.filter(project => !project.is_fixture).map(project => ({ project, blockers: [] }))

  useEffect(() => {
    if (!projects.length) return
    if (!a || !projects.some(p => p.project_id === a)) setA(projects[0].project_id)
    if (!b || !projects.some(p => p.project_id === b)) setB(projects.find(p => p.utility_id !== projects[0].utility_id)?.project_id ?? projects[1]?.project_id ?? projects[0].project_id)
  }, [projects, a, b])

  useEffect(() => {
    if (!a || !b) return
    const first = projects.find(p => p.project_id === a), second = projects.find(p => p.project_id === b)
    if (!first || !second) return
    setAssessmentError('')
    if (!live) { setAssessment(null); return }
    let active = true
    getAssessment(a, b).then(result => { if (active) setAssessment(result) }).catch(cause => {
      if (active) { setAssessment(null); setAssessmentError((cause as Error).message) }
    })
    return () => { active = false }
  }, [a, b, projects, live])

  return <main className="workspace-page content-width">
    <div className="workspace-heading"><div><span className="eyebrow dark"><span className="eyebrow-line" /> PROJECT INTELLIGENCE</span><h1>Location Workbench</h1><p>Verify project sites, explain exclusions, and find the right pair before a manager reviews coordination.</p></div><button className="button button-outline" onClick={onReload} disabled={loading}><RefreshCw size={16} className={loading ? 'spin' : ''} /> Refresh records</button></div>
    {!live && <div className="notice preview"><Database size={18} /><span>{apiError || (loading ? 'Loading the SYNCHRO API…' : 'The review pipeline is unavailable.')}</span></div>}
    <div className="workspace-kpis"><div><span>NEED LOCATION REVIEW</span><strong>{live ? queue.total.toString().padStart(2, '0') : '—'}</strong><small>From the review API</small></div><div><span>CURRENT PROJECT RECORDS</span><strong>{projectsLoaded ? projects.filter(p => !p.is_fixture).length.toString().padStart(2, '0') : '—'}</strong><small>Loaded from project versions</small></div><div><span>SPATIAL RULE</span><strong>{live ? `< ${maximumMeters / 1000}` : '—'} <i>{live ? 'km' : ''}</i></strong><small>From the configured API</small></div></div>
    <div className="workbench-grid">
      <section className="panel review-panel"><div className="panel-head"><div><h2>{live ? 'Excluded Projects' : 'Current Projects'}</h2><p>{live ? 'What needs to be checked before these projects qualify.' : 'Live project versions are shown while the review service is unavailable.'}</p></div><span className="count-pill">{live ? `${queue.total} to review` : `${visibleRows.length} records`}</span></div>
        <div className="review-list">{visibleRows.length === 0 ? <div className="empty-state"><CheckCircle2 size={30} /><strong>{live ? 'No location blockers' : 'No project records loaded'}</strong><span>{live ? 'Current records are ready for qualified pair search.' : 'Connect the project API or refresh records.'}</span></div> : visibleRows.map(row => <button key={row.project.project_id} className={`review-item ${selected?.project_id === row.project.project_id ? 'selected' : ''}`} onClick={() => setSelectedId(row.project.project_id)}><span className="utility-avatar">{row.project.utility_id === 'DESC' ? 'D' : row.project.utility_id === 'GPC' ? 'G' : row.project.utility_id.slice(0, 1)}</span><span className="review-item-copy"><strong>{row.project.project_name}</strong><small>{row.project.utility_id} · {row.project.location_text}</small><span className="badge-row">{live ? row.blockers.slice(0, 2).map(code => <em key={code} className="badge amber">{blockerNames[code] ?? code}</em>) : <em className="badge neutral">{row.project.validation_state.replaceAll('_', ' ')}</em>}{live && row.blockers.length > 2 && <em className="badge neutral">+{row.blockers.length - 2}</em>}</span></span><ArrowRight size={17} /></button>)}</div>
      </section>
      <section className="panel detail-panel"><AnimatePresence mode="wait">{selected ? <motion.div key={selected.project_id} initial={reduce ? undefined : { opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={reduce ? undefined : { opacity: 0, y: -8 }} transition={{ duration: .22 }}>
        <div className="panel-head"><div><span className="detail-kicker">RECORD DETAIL / {selected.utility_id}</span><h2>{selected.project_name}</h2></div><span className="badge amber">{selected.validation_state.replaceAll('_', ' ')}</span></div>
        <p className="detail-location"><MapPin size={16} /> {selected.location_text}</p>
        <div className="detail-facts"><div><span>GEOMETRY QUALITY</span><strong>{selected.geometry_quality}</strong></div><div><span>VALIDATION</span><strong>{selected.validation_state.replaceAll('_', ' ')}</strong></div><div><span>PROJECT STATUS</span><strong>{selected.status.replaceAll('_', ' ')}</strong></div><div><span>VERSION</span><strong>{selected.version_id}</strong></div></div>
        {(selected.geometry_origin === 'CENTER_POINT' || selected.geometry_quality === 'UNRESOLVED') && <div className="detail-alert"><ShieldAlert size={18} /><p>This coordinate is a reference location or unresolved geometry. It has not been confirmed as the {selected.project_name} site.</p></div>}
        <h3 className="detail-subhead">Source evidence</h3><SourceList project={selected} />
        <button className="button button-primary detail-action" onClick={() => setVerify(true)} disabled={!live}>Verify project location <ArrowRight size={17} /></button>
      </motion.div> : <div className="empty-state"><MapPin size={30} /><strong>Select a project</strong><span>Its review blockers and source evidence will appear here.</span></div>}</AnimatePresence></section>
    </div>
    <section className="comparison-section"><div className="panel-head"><div><span className="eyebrow dark">DISTANCE EXPLAINED</span><h2>Compare two records</h2><p>See exactly what the current coordinates can and cannot establish.</p></div></div>
      <div className="compare-grid"><div className="compare-controls"><label>PROJECT A<select value={a} onChange={e => setA(e.target.value)}>{projects.map(p => <option value={p.project_id} key={p.project_id}>{p.utility_id} · {p.project_name}</option>)}</select></label><label>PROJECT B<select value={b} onChange={e => setB(e.target.value)}>{projects.map(p => <option value={p.project_id} key={p.project_id}>{p.utility_id} · {p.project_name}</option>)}</select></label>
          {assessment && <div className="comparison-result"><span>SUPPLIED-GEOMETRY SEPARATION</span><strong>{assessment.distance ? `${(assessment.distance.meters / 1000).toFixed(2)} km` : 'Unavailable'}</strong><p>{assessment.distance?.kind === 'REFERENCE_POINT_SEPARATION' ? 'Distance between reference points. This is not a verified project-to-project distance.' : assessment.distance ? 'Measured between supplied project geometries.' : 'Both records need geometry before distance can be measured.'}</p><div className="threshold-track"><span style={{ width: `${Math.min(100, assessment.distance ? assessment.distance.meters / assessment.maximum_meters * 100 : 0)}%` }} /></div><small>Strictly under {(assessment.maximum_meters / 1000).toFixed(1)} km required · {assessment.qualifies ? 'Qualifies' : 'No qualified opportunity'}</small></div>}
          {assessmentError && <div className="notice error">{assessmentError}</div>}
        </div><MapPanel projects={projects.filter(p => p.project_id === a || p.project_id === b)} compact /></div>
    </section>
    <AnimatePresence>{verify && selected && <VerificationPanel key={selected.project_id} project={selected} live={live} accessKey={accessKey} onClose={() => setVerify(false)} onSaved={onReload} />}</AnimatePresence>
  </main>
}
