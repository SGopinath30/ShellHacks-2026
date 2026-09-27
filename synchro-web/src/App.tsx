import { useCallback, useEffect, useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { ArrowRight, Menu, X } from 'lucide-react'
import { getProjects, getQualifiedPairs, getReviewQueue } from './api'
import Landing from './Landing'
import Opportunities from './Opportunities'
import Workbench from './Workbench'
import type { Project, QualifiedPairs, ReviewQueue } from './types'

type Page = 'home' | 'workbench' | 'opportunities'
const emptyPairs: QualifiedPairs = { maximum_meters: 0, total: 0, opportunities: [] }

function currentPage(): Page {
  const hash = window.location.hash.replace('#', '')
  return hash === 'workbench' || hash === 'opportunities' ? hash : 'home'
}

export default function App() {
  const reduce = useReducedMotion()
  const [page, setPage] = useState<Page>(currentPage)
  const [menu, setMenu] = useState(false)
  const [projects, setProjects] = useState<Project[]>([])
  const [queue, setQueue] = useState<ReviewQueue>({ total: 0, projects: [] })
  const [pairs, setPairs] = useState<QualifiedPairs>(emptyPairs)
  const [live, setLive] = useState(false)
  const [projectsLoaded, setProjectsLoaded] = useState(false)
  const [apiError, setApiError] = useState('')
  const [loading, setLoading] = useState(true)
  const [accessKey, setAccessKey] = useState('')
  const [keyOpen, setKeyOpen] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setApiError('')
    try {
      const nextProjects = await getProjects()
      setProjects(nextProjects)
      setProjectsLoaded(true)
      try {
        const [nextQueue, nextPairs] = await Promise.all([getReviewQueue(), getQualifiedPairs()])
        setQueue(nextQueue); setPairs(nextPairs); setLive(true)
      } catch (cause) {
        setQueue({ total: 0, projects: [] }); setPairs(emptyPairs); setLive(false)
        setApiError(`The deployed API returned project records, but its location review or qualified pair routes are unavailable. ${String((cause as Error).message)} Deploy the current gridlock-control-plane backend to enable the full workflow.`)
      }
    } catch (cause) {
      setProjects([]); setProjectsLoaded(false); setQueue({ total: 0, projects: [] }); setPairs(emptyPairs); setLive(false)
      setApiError(`Project records could not be loaded. ${String((cause as Error).message)}`)
    } finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])
  useEffect(() => {
    const update = () => { setPage(currentPage()); setMenu(false); window.scrollTo({ top: 0, behavior: 'instant' }) }
    window.addEventListener('hashchange', update)
    return () => window.removeEventListener('hashchange', update)
  }, [])
  useEffect(() => {
    if (!window.matchMedia('(hover: hover) and (pointer: fine)').matches) return
    const surfaces = '.hero-map-frame,.hero-float-card,.ribbon-inner>div,.stage-card,.feature-mini-card,.workspace-kpis>div,.detail-facts>div,.detail-alert,.source-row,.notice,.comparison-result,.decision-preview>div>div,.opportunity-empty,.opportunity-summary>div,.opportunity-notes>div,.evidence-group,.review-item,.opportunity-item,.map-panel'
    const track = (event: PointerEvent) => {
      const target = event.target instanceof Element ? event.target.closest<HTMLElement>(surfaces) : null
      if (!target) return
      const bounds = target.getBoundingClientRect()
      target.style.setProperty('--hover-x', `${event.clientX - bounds.left}px`)
      target.style.setProperty('--hover-y', `${event.clientY - bounds.top}px`)
    }
    document.addEventListener('pointermove', track, { passive: true })
    return () => document.removeEventListener('pointermove', track)
  }, [])

  return <div className={`site-shell ${page === 'home' ? 'site-home' : 'site-app'}`}>
    <header className="site-header"><div className="content-width header-inner">
      <a href="#home" className="brand" aria-label="SYNCHRO home"><span className="brand-mark"><i /><i /><i /></span><span>SYNCHRO<small>GRID COORDINATION</small></span></a>
      <nav className={menu ? 'nav-links open' : 'nav-links'} aria-label="Main navigation"><a className={page === 'home' ? 'active' : ''} href="#home">Platform</a><a className={page === 'workbench' ? 'active' : ''} href="#workbench">Location Workbench</a><a className={page === 'opportunities' ? 'active' : ''} href="#opportunities">Opportunities</a></nav>
      <div className="header-actions"><span className={`system-status ${live ? 'online' : ''}`}><i /> {loading ? 'Checking data' : live ? 'API connected' : projectsLoaded ? 'API needs update' : 'API unavailable'}</span><button className="button button-small access-trigger" type="button" onClick={() => setKeyOpen(value => !value)} aria-expanded={keyOpen}>{accessKey ? 'Reviewer key set' : 'Reviewer access'}</button><a className="button button-small" href={page === 'home' ? '#workbench' : '#opportunities'}>{page === 'home' ? 'Enter workspace' : 'View opportunities'} <ArrowRight size={15} /></a><button className="mobile-menu" onClick={() => setMenu(value => !value)} aria-label={menu ? 'Close menu' : 'Open menu'}>{menu ? <X size={22} /> : <Menu size={22} />}</button></div>
    </div></header>
    {keyOpen && <div className="access-bar content-width"><label>API reviewer key <input type="password" autoComplete="off" value={accessKey} onChange={event => setAccessKey(event.target.value.trim())} placeholder="Enter key for protected actions" /></label><button type="button" className="button button-small" onClick={() => { setAccessKey(''); setKeyOpen(false) }}>Clear key</button><small>Held in this tab only. Enter it on a trusted device; the API still records reviewer IDs supplied in each form.</small></div>}
    <AnimatePresence mode="wait"><motion.div key={page} initial={reduce ? undefined : { opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={reduce ? undefined : { opacity: 0, y: -10 }} transition={{ duration: .25 }}>
      {page === 'home' ? <Landing projects={projects} queue={queue} pairs={pairs} live={live} loading={loading} /> : page === 'workbench' ? <Workbench projects={projects} queue={queue} maximumMeters={pairs.maximum_meters} live={live} projectsLoaded={projectsLoaded} apiError={apiError} loading={loading} onReload={load} accessKey={accessKey} /> : <Opportunities data={pairs} live={live} apiError={apiError} accessKey={accessKey} />}
    </motion.div></AnimatePresence>
    <footer className="site-footer"><div className="content-width footer-inner"><div><span className="footer-brand">SYNCHRO</span><p>Evidence before coordination.</p></div><div><span>BUILT FOR REGIONAL TRANSMISSION PLANNING</span><small>Source-backed locations · Measured proximity · Traceable decisions</small></div></div></footer>
  </div>
}
