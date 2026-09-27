import { lazy, Suspense, useState } from 'react'
import { ArrowRight, CircleCheck, Compass, FileClock, Layers3, MapPin, ShieldCheck, Sparkles } from 'lucide-react'
import { motion, useReducedMotion } from 'motion/react'
import MapPanel from './MapPanel'
import type { Project, QualifiedPairs, ReviewQueue } from './types'
import { formatMiles } from './utils'

const stages = [
  { number: '01', title: 'Detect', icon: Compass, copy: 'Find cross-utility projects inside a measured spatial threshold.' },
  { number: '02', title: 'Verify', icon: ShieldCheck, copy: 'Keep reference points and unresolved locations out of qualified results.' },
  { number: '03', title: 'Decide', icon: FileClock, copy: 'Give managers evidence, analysis context, and a lasting decision record.' },
]
const AeroShards = lazy(() => import('./components/AeroShards/AeroShards'))

export default function Landing({ projects, queue, pairs, live, loading }: {
  projects: Project[]; queue: ReviewQueue; pairs: QualifiedPairs; live: boolean; loading: boolean
}) {
  const reduce = useReducedMotion()
  const [aeroFailed, setAeroFailed] = useState(false)
  const enter = reduce ? {} : { initial: { opacity: 0, y: 22 }, animate: { opacity: 1, y: 0 } }
  return <>
    <main>
      <section className="hero content-width">
        {!aeroFailed && <Suspense fallback={null}><AeroShards
          className="hero-aero-shards"
          backgroundColor="#0b303a"
          shardColor="#55bba7"
          accentColor="#a4e6cb"
          placement="full"
          flow="stream"
          material="satin"
          detail="bold"
          density={0.7}
          shardSize={0.85}
          speed={0.55}
          spin={0.45}
          spread={0.9}
          glow={0.65}
          bloom={0.18}
          grain={0}
          chromaticAberration={0}
          interaction="repel"
          interactionStrength={0.35}
          rippleIntensity={0.4}
          holdToGather={false}
          paused={Boolean(reduce)}
          onError={() => setAeroFailed(true)}
        /></Suspense>}
        <div className="hero-copy">
          <motion.div {...enter} transition={{ duration: .5 }} className="eyebrow"><span className="eyebrow-line" /> THE COORDINATION LAYER FOR GRID PLANNING</motion.div>
          <motion.h1 {...enter} transition={{ duration: .6, delay: .08 }}>Every utility sees its plan.<br /><em>See the space between.</em></motion.h1>
          <motion.p {...enter} transition={{ duration: .6, delay: .16 }} className="hero-description">SYNCHRO connects source-backed project data, geospatial analysis, and manager decisions to reveal where utilities may coordinate construction.</motion.p>
          <motion.div {...enter} transition={{ duration: .6, delay: .23 }} className="hero-actions">
            <a className="button button-primary" href="#workbench">Open Location Workbench <ArrowRight size={17} /></a>
            <a className="button button-ghost" href="#opportunities">Explore opportunities</a>
          </motion.div>
          <motion.div {...enter} transition={{ duration: .6, delay: .3 }} className="hero-trust"><CircleCheck size={15} /> Source-backed by design <span /> <CircleCheck size={15} /> Human decisions preserved</motion.div>
        </div>
        <motion.div {...enter} transition={{ duration: .75, delay: .2 }} className="hero-visual">
          <div className="hero-map-frame">
            <div className="window-chrome"><span /><span /><span /><p>SYNCHRO / CURRENT PROJECT RECORDS</p><div className="live-dot" /></div>
            <MapPanel projects={projects.filter(project => !project.is_fixture)} compact />
          </div>
          <motion.div className="hero-float-card" animate={reduce ? undefined : { y: [0, -7, 0] }} transition={{ duration: 5, repeat: Infinity }}>
            <span className="float-icon"><MapPin size={17} /></span>
            <div><strong>{live ? `${queue.total} locations need review` : 'Pipeline status needs attention'}</strong><small>{loading ? 'Loading project records' : live ? `${pairs.total} qualified opportunities` : 'Review endpoints are unavailable'}</small></div>
          </motion.div>
          <div className="hero-visual-caption">Current API records. Reference coordinates remain excluded until project sites are verified.</div>
        </motion.div>
      </section>

      <section className="metric-ribbon"><div className="content-width ribbon-inner">
        <div><strong>{live ? `< ${formatMiles(pairs.maximum_meters, 1)} mi` : '—'}</strong><span>API spatial filter</span></div>
        <div><strong>{loading ? '—' : projects.filter(project => !project.is_fixture).length}</strong><span>Current source records</span></div>
        <div><strong>{live ? queue.total : '—'}</strong><span>Locations needing review</span></div>
        <div><strong>{live ? pairs.total : '—'}</strong><span>Qualified opportunities</span></div>
      </div></section>

      <section className="section-pad content-width">
        <div className="section-intro"><span className="eyebrow dark"><span className="eyebrow-line" /> THE WORKFLOW</span><h2>From scattered plans to<br /><em>reviewable decisions.</em></h2><p>One connected flow from project evidence to manager action. Uncertainty stays visible at every stage.</p></div>
        <div className="stage-grid">
          {stages.map((stage, i) => <motion.article className="stage-card" key={stage.title}
            initial={reduce ? undefined : { opacity: 0, y: 22 }} whileInView={reduce ? undefined : { opacity: 1, y: 0 }} viewport={{ once: true, amount: .25 }} transition={{ duration: .45, delay: i * .1 }}>
            <div className="stage-top"><span>{stage.number}</span><stage.icon size={22} /></div>
            <h3>{stage.title}</h3><p>{stage.copy}</p><div className="stage-bottom"><span>VIEW LAYER</span><ArrowRight size={16} /></div>
          </motion.article>)}
        </div>
      </section>

      <section className="feature-band"><div className="content-width feature-band-inner">
        <div className="feature-copy"><span className="eyebrow"><span className="eyebrow-line" /> BUILT FOR TRANSMISSION PLANNERS</span><h2>Clear enough to act.<br /><em>Detailed enough to defend.</em></h2><p>Each opportunity carries project versions, geometry provenance, timing context, and source evidence. The Decision Ledger records what a manager saw and why they acted.</p><a className="text-link" href="#opportunities">View the decision flow <ArrowRight size={17} /></a></div>
        <div className="feature-stack"><div className="feature-mini-card"><Layers3 size={19} /><div><strong>Measured proximity</strong><small>Strict distance threshold and geometry quality</small></div><span>01</span></div><div className="feature-mini-card"><ShieldCheck size={19} /><div><strong>Source-backed verification</strong><small>Current project versions and review blockers</small></div><span>02</span></div><div className="feature-mini-card"><FileClock size={19} /><div><strong>Decision Ledger</strong><small>Append-only actions with analysis snapshots</small></div><span>03</span></div></div>
      </div></section>

      <section className="closing-cta content-width"><div><span className="eyebrow dark"><Sparkles size={14} /> START WITH THE EVIDENCE</span><h2>See what is ready.<br />See what still needs review.</h2></div><a className="button button-primary" href="#workbench">Launch workbench <ArrowRight size={17} /></a></section>
    </main>
  </>
}
