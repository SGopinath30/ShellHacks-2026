import { useEffect, useState } from 'react'
import { api, type VerificationInput } from './api'
import type { Project } from './types'
import { safeSourceUrl } from './utils'
import MapPanel from './MapPanel'

type Proposal = {
  summary: string; missing_evidence: string[]; outreach_draft: string
  verification: VerificationInput | null
}
type Research = {
  proposal_id: string; base_version_id: string; proposal_hash: string; revision: number
  state: 'RUNNING' | 'REVIEW' | 'FAILED' | 'REJECTED' | 'APPLIED'
  payload: Partial<Proposal>; error: string | null; created_at: string
  research: { gis?: { state: string; note: string; source_url?: string }; model?: string; retrieved_on?: string; report?: string; grounding?: {
    groundingChunks?: { web?: { uri: string; title: string } }[]
    groundingSupports?: { segment?: { text?: string }; groundingChunkIndices?: number[] }[]
    searchEntryPoint?: { renderedContent?: string }
  } }
}

function ProposalEditor({ value, onChange, baseVersion }: { value: string; onChange: (value: string) => void; baseVersion: string }) {
  const proposal = JSON.parse(value) as Proposal
  const update = (next: Proposal) => onChange(JSON.stringify(next, null, 2))
  const verification = proposal.verification
  const field = (name: string, val: unknown) => verification && update({ ...proposal, verification: { ...verification, [name]: val } })
  const evidence = (kind: 'geometry_evidence' | 'status_evidence', name: string, val: string) => {
    if (!verification) return
    field(kind, { source_id: '', source_name: '', source_url: '', ...verification[kind], [name]: val })
  }
  return <div className="verify-form">
    <label>Research summary<textarea value={proposal.summary} onChange={event => update({ ...proposal, summary: event.target.value })} /></label>
    <label>Missing evidence (one item per line)<textarea value={proposal.missing_evidence.join('\n')} onChange={event => update({ ...proposal, missing_evidence: event.target.value.split('\n').filter(item => item.trim()) })} /></label>
    <label>Utility inquiry draft<textarea value={proposal.outreach_draft} onChange={event => update({ ...proposal, outreach_draft: event.target.value })} /></label>
    {!verification && <button type="button" className="button button-outline" onClick={() => update({ ...proposal, verification: {
      base_version_id: baseVersion, actor_id: 'Pending human review', actor_role: 'Research proposal', reason: '', location_text: '',
      geometry: { type: 'Point', coordinates: [null, null] } as unknown as VerificationInput['geometry'], geometry_origin: 'MANUAL_VERIFIED', geometry_quality: 'APPROXIMATE',
      geometry_evidence: { source_id: '', source_name: '', source_url: '', page_or_row: '' },
    } })}>Add source-backed location proposal</button>}
    {verification && <>
      <label>Location description<input value={verification.location_text} onChange={event => field('location_text', event.target.value)} /></label>
      <label>How this site was identified<textarea value={verification.reason} onChange={event => field('reason', event.target.value)} /></label>
      <p>Enter the actual source coordinates in WGS84 longitude and latitude. Both values are required.</p>
      {verification.geometry.type === 'Point' ? <div className="form-grid two">
        <label>Longitude<input type="number" min="-180" max="180" step="any" value={verification.geometry.coordinates[0] ?? ''} onChange={event => field('geometry', { type: 'Point', coordinates: [event.target.value === '' ? null : Number(event.target.value), verification.geometry.coordinates[1]] })} /></label>
        <label>Latitude<input type="number" min="-90" max="90" step="any" value={verification.geometry.coordinates[1] ?? ''} onChange={event => field('geometry', { type: 'Point', coordinates: [verification.geometry.coordinates[0], event.target.value === '' ? null : Number(event.target.value)] })} /></label>
      </div> : <p>Line geometry is preserved. Use the manual verification workflow to change its route.</p>}
      <label>Geometry origin<select value={verification.geometry_origin} onChange={event => field('geometry_origin', event.target.value)}>{['UTILITY_GIS', 'PUBLIC_GIS', 'OSM_MATCH', 'SINGLE_LOCATED_POINT', 'MANUAL_VERIFIED', 'TWO_ENDPOINT_SEGMENT'].map(val => <option key={val}>{val}</option>)}</select></label>
      <label>Geometry quality<select value={verification.geometry_quality} onChange={event => field('geometry_quality', event.target.value)}>{['APPROXIMATE', 'HIGH', 'AUTHORITATIVE'].map(val => <option key={val}>{val}</option>)}</select></label>
      <h4>Geometry evidence</h4>
      {(['source_id', 'source_name', 'source_url', 'page_or_row', 'snippet'] as const).map(name => <label key={name}>{name.replaceAll('_', ' ')}<input value={verification.geometry_evidence[name] ?? ''} onChange={event => evidence('geometry_evidence', name, event.target.value)} /></label>)}
      <label>Proposed status<select value={verification.status ?? ''} onChange={event => field('status', event.target.value || null)}><option value="">Keep current status</option>{['proposed', 'planned', 'approved', 'in_progress', 'under_construction', 'on_hold', 'cancelled', 'completed', 'operational', 'unknown'].map(val => <option key={val}>{val}</option>)}</select></label>
      {verification.status && <><h4>Status evidence</h4>{(['source_id', 'source_name', 'source_url', 'snippet'] as const).map(name => <label key={name}>{name.replaceAll('_', ' ')}<input value={verification.status_evidence?.[name] ?? ''} onChange={event => evidence('status_evidence', name, event.target.value)} /></label>)}</>}
    </>}
  </div>
}

export default function ResearchPanel({ project, accessKey, live, onSaved }: {
  project: Project; accessKey: string; live: boolean; onSaved: () => Promise<void>
}) {
  const [rows, setRows] = useState<Research[]>([])
  const [selected, setSelected] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [actor, setActor] = useState('')
  const [reason, setReason] = useState('')
  const [confirmed, setConfirmed] = useState(false)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const headers = { 'X-API-Key': accessKey }
  const current = rows.find(row => row.proposal_id === selected) ?? rows[0]
  const verification = current?.payload.verification
  const sources = current?.research.grounding?.groundingChunks ?? []
  const stale = current && current.base_version_id !== project.version_id

  useEffect(() => {
    if (!accessKey || !live) { setRows([]); return }
    let active = true
    const load = async () => {
      try {
        const data = await api<Research[]>(`/projects/${encodeURIComponent(project.project_id)}/research`, { headers: { 'X-API-Key': accessKey } })
        if (active) setRows(data)
      } catch (cause) { if (active) setError((cause as Error).message) }
    }
    void load()
    const timer = window.setInterval(() => { void load() }, 5000)
    return () => { active = false; window.clearInterval(timer) }
  }, [project.project_id, accessKey, live])

  useEffect(() => { setConfirmed(false); setEditing(false) }, [current?.proposal_hash])

  async function perform(work: () => Promise<void>) {
    setBusy(true); setError('')
    try { await work() } catch (cause) { setError((cause as Error).message) } finally { setBusy(false) }
  }
  function replace(row: Research) {
    setRows(previous => [row, ...previous.filter(item => item.proposal_id !== row.proposal_id)])
    setSelected(row.proposal_id)
    setConfirmed(false)
  }
  const start = () => perform(async () => {
    replace(await api<Research>(`/projects/${encodeURIComponent(project.project_id)}/research`, { method: 'POST', headers }))
  })
  const save = () => perform(async () => {
    if (!current) return
    const proposal: unknown = JSON.parse(draft)
    replace(await api<Research>(`/research/${current.proposal_id}`, { method: 'PUT', headers,
      body: JSON.stringify({ proposal_hash: current.proposal_hash, actor_id: actor, reason, proposal }) }))
    setEditing(false)
  })
  const decide = (action: 'APPROVE' | 'REJECT') => perform(async () => {
    if (!current) return
    const result = await api<{ proposal: Research }>(`/research/${current.proposal_id}/review`, {
      method: 'POST', headers, body: JSON.stringify({ proposal_hash: current.proposal_hash,
        actor_id: actor, reason, action, evidence_confirmed: confirmed }),
    })
    replace(result.proposal)
    if (action === 'APPROVE') await onSaved()
  })
  const preview = verification ? { ...project, geometry: verification.geometry,
    geometry_origin: verification.geometry_origin, geometry_quality: 'UNRESOLVED' as const,
    location_text: verification.location_text } : null

  return <section className="research-panel" aria-label="AI research and human review">
    <h3>Research with AI</h3>
    <p>Gemini gathers public evidence and drafts a proposal. Review the actual sources before approving any changes.</p>
    {!accessKey && <p>Enter your reviewer key under Reviewer access to research or review.</p>}
    <button className="button button-outline" disabled={!live || !accessKey || busy || rows.some(row => row.state === 'RUNNING')}
      onClick={start}>{rows.some(row => row.state === 'RUNNING') ? 'Researching public sources…' : 'Research with Gemini'}</button>
    {error && <div className="notice error" role="alert">{error}</div>}
    {rows.length > 0 && <label>Saved research<select value={current?.proposal_id ?? ''} onChange={event => { setSelected(event.target.value); setEditing(false); setConfirmed(false) }}>
      {rows.map(row => <option key={row.proposal_id} value={row.proposal_id}>{new Date(row.created_at).toLocaleString()} · {row.state} · revision {row.revision}</option>)}
    </select></label>}
    {current && <div>
      <p><strong>{current.state}</strong> · Base version: {current.base_version_id}</p>
      {current.state === 'RUNNING' && <p role="status">Research is running. You may leave this page and return to the saved result.</p>}
      {current.error && <p role="alert">{current.error}</p>}
      {current.payload.summary && <p style={{ whiteSpace: 'pre-wrap' }}>{current.payload.summary}</p>}
      {!!current.payload.missing_evidence?.length && <div className="notice caution"><div><strong>Evidence still needed</strong><ul>{current.payload.missing_evidence.map((item, i) => <li key={i}>{item}</li>)}</ul></div></div>}
      {current.research.gis && <p>County GIS: {current.research.gis.state} — {current.research.gis.note} {safeSourceUrl(current.research.gis.source_url) && <a href={safeSourceUrl(current.research.gis.source_url)!} target="_blank" rel="noopener noreferrer">View GIS query</a>}</p>}
      {sources.length > 0 && <div><h4>Retrieved sources</h4><ol>{sources.map((source, i) => {
        const url = safeSourceUrl(source.web?.uri)
        return <li key={i}>{url ? <a href={url} target="_blank" rel="noopener noreferrer">{source.web?.title || url}</a> : 'Source unavailable'}</li>
      })}</ol></div>}
      {current.research.grounding?.groundingSupports?.map((support, i) => <blockquote key={i}>
        {support.segment?.text} {(support.groundingChunkIndices ?? []).map(index => {
          const url = safeSourceUrl(sources[index]?.web?.uri)
          return url ? <a key={index} href={url} target="_blank" rel="noopener noreferrer"> [{index + 1}]</a> : null
        })}
      </blockquote>)}
      {current.research.grounding?.searchEntryPoint?.renderedContent && <iframe title="Google Search suggestions" sandbox="allow-popups allow-popups-to-escape-sandbox" referrerPolicy="no-referrer"
        srcDoc={current.research.grounding.searchEntryPoint.renderedContent} style={{ border: 0, width: '100%', height: 180 }} />}
      {current.research.report && <details><summary>Full research report · {current.research.model} · {current.research.retrieved_on}</summary><pre className="research-text">{current.research.report}</pre></details>}
      {verification && <div><h4>Proposed changes — unverified</h4>
        <p>Status: {project.status} → {verification.status || project.status}</p>
        <p>Location: {verification.location_text}</p><p>Proposed quality: {verification.geometry_quality}</p>
        <pre className="research-text">{JSON.stringify(verification.geometry, null, 2)}</pre>
        {[verification.geometry_evidence, verification.status_evidence].filter(Boolean).map((source, i) => {
          const url = safeSourceUrl(source?.source_url)
          return <p key={i}>{url && <a href={url} target="_blank" rel="noopener noreferrer">{source?.source_name}</a>} · {source?.page_or_row} {source?.snippet}</p>
        })}
        {preview && <MapPanel projects={[preview]} compact />}
        <details><summary>Exact verification payload</summary><pre className="research-text">{JSON.stringify(verification, null, 2)}</pre></details>
      </div>}
      {current.payload.outreach_draft && <details><summary>Utility inquiry draft — send manually</summary><pre className="research-text">{current.payload.outreach_draft}</pre></details>}
      {current.state === 'REVIEW' && <div className="verify-form">
        {stale && <div className="notice caution">Project changed since this research. Start a new research request before approval.</div>}
        <label>Reviewer ID<input value={actor} onChange={event => setActor(event.target.value)} /></label>
        <label>Review reason<textarea value={reason} onChange={event => setReason(event.target.value)} /></label>
        <p>Reviewer IDs are recorded as entered; access uses the team's shared reviewer key.</p>
        <button className="button button-outline" disabled={busy} onClick={() => { setEditing(!editing); setDraft(JSON.stringify(current.payload, null, 2)); setConfirmed(false) }}>{editing ? 'Cancel editing' : 'Edit evidence proposal'}</button>
        {editing && <><ProposalEditor value={draft} onChange={setDraft} baseVersion={current.base_version_id} />
          <p>Resolve missing evidence with source-backed values. Save edits, then review the updated proposal before approving.</p>
          <button className="button button-outline" disabled={busy || !actor.trim() || !reason.trim()} onClick={save}>Save proposal revision</button></>}
        <label className="research-confirm"><input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} />I reviewed the sources and confirm this project's location, geometry quality, and proposed current status.</label>
        <button className="button button-primary" disabled={busy || editing || !confirmed || !verification || !!current.payload.missing_evidence?.length || stale || !actor.trim() || !reason.trim()} onClick={() => decide('APPROVE')}>Approve and apply reviewed proposal</button>
        <button className="button button-outline" disabled={busy || editing || !actor.trim() || !reason.trim()} onClick={() => decide('REJECT')}>Reject proposal</button>
      </div>}
    </div>}
  </section>
}
