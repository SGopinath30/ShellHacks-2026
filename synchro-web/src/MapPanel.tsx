import { motion, useReducedMotion } from 'motion/react'
import { MapPin, Maximize2 } from 'lucide-react'
import type { Project } from './types'

export default function MapPanel({ projects, compact = false }: { projects: Project[]; compact?: boolean }) {
  const reduce = useReducedMotion()
  const coordinates = projects.flatMap(project => project.geometry?.type === 'Point'
    ? [project.geometry.coordinates]
    : project.geometry?.type === 'LineString' ? project.geometry.coordinates : [])
  const longitudes = coordinates.map(point => point[0])
  const latitudes = coordinates.map(point => point[1])
  const centerLon = coordinates.length ? (Math.min(...longitudes) + Math.max(...longitudes)) / 2 : -81.25
  const centerLat = coordinates.length ? (Math.min(...latitudes) + Math.max(...latitudes)) / 2 : 32.5
  const lonSpan = Math.max(0.8, (Math.max(...longitudes) - Math.min(...longitudes)) * 1.35 || 0)
  const latSpan = Math.max(0.8, (Math.max(...latitudes) - Math.min(...latitudes)) * 1.35 || 0)
  const coordinateToPoint = ([lon, lat]: [number, number]) => ({
    x: 340 + (lon - centerLon) / lonSpan * 620,
    y: 220 - (lat - centerLat) / latSpan * 380,
  })
  const points = projects.map(project => ({ project, point: project.geometry?.type === 'Point' ? coordinateToPoint(project.geometry.coordinates) : null })).filter(item => item.point !== null)
  const lines = projects.filter(project => project.geometry?.type === 'LineString')
  const hasReference = projects.some(project => project.geometry_origin === 'CENTER_POINT' || project.geometry_quality === 'UNRESOLVED')
  const hasGeometry = points.length > 0 || lines.length > 0
  return (
    <div className={`map-panel ${compact ? 'map-panel-compact' : ''}`}>
      <div className="map-topline">
        <div className="map-topline-title"><MapPin size={15} /> Southeast coordinate view</div>
        <span className="map-scale"><Maximize2 size={13} /> Reference view</span>
      </div>
      <div className="map-canvas">
        <svg viewBox="0 0 680 440" role="img" aria-label="Coordinate plot of current projects in the Southeast">
          <defs>
            <pattern id="minor-grid" width="40" height="40" patternUnits="userSpaceOnUse"><path d="M 40 0 L 0 0 0 40" fill="none" stroke="#6a94a0" strokeOpacity=".12" strokeWidth="1" /></pattern>
            <linearGradient id="map-glow" x1="0" y1="0" x2="1" y2="1"><stop stopColor="#0c4650"/><stop offset="1" stopColor="#0a303b"/></linearGradient>
          </defs>
          <rect width="680" height="440" fill="url(#map-glow)" />
          <rect width="680" height="440" fill="url(#minor-grid)" />
          <path className="map-contour" d="M-30 366C88 332 96 415 236 372S396 279 507 322 648 331 718 269M-40 289C62 250 117 327 227 283S395 207 531 237 632 231 717 195M-28 204C80 156 141 233 267 184S414 124 548 147 654 146 711 99M-20 115C96 62 133 137 274 96S476 53 555 69 647 69 711 17" />
          <path d="M84 21C114 101 95 153 157 212s59 107 91 235M478-16c-26 85-4 133 39 181s52 118 39 279" fill="none" stroke="#75aeb4" strokeOpacity=".13" strokeWidth="2" />
          {[30, 110, 190, 270, 350, 430].map(y => <text key={y} x="12" y={y + 8} fill="#80aab1" opacity=".55" fontSize="9">{(centerLat + (220 - y) / 380 * latSpan).toFixed(1)}°N</text>)}
          {lines.map(project => project.geometry?.type === 'LineString' && <path className="map-project-line" key={project.project_id}
            d={project.geometry.coordinates.map((coordinate, index) => {
              const point = coordinateToPoint(coordinate)
              return `${index === 0 ? 'M' : 'L'}${point.x} ${point.y}`
            }).join(' ')} fill="none" stroke={project.geometry_quality === 'UNRESOLVED' ? '#f4b86b' : '#7be2c4'}
            strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><title>{`${project.project_name} · ${project.geometry_quality} geometry`}</title></path>)}
          {points.map(({ project, point }, index) => point && (
            <g className="map-project-marker" key={project.project_id} transform={`translate(${point.x} ${point.y})`}>
              <title>{`${project.project_name} · ${project.geometry_quality} geometry`}</title>
              <motion.circle r="24" fill={project.geometry_quality === 'UNRESOLVED' ? '#f6bc74' : '#7be2c4'} fillOpacity=".08" stroke={project.geometry_quality === 'UNRESOLVED' ? '#f6bc74' : '#7be2c4'} strokeOpacity=".35" strokeDasharray="3 4"
                animate={reduce ? undefined : { r: [22, 29, 22], opacity: [.7, 1, .7] }} transition={{ duration: 4, repeat: Infinity, delay: index * 1.4 }} />
              <circle r="6" fill={project.geometry_quality === 'UNRESOLVED' ? '#f4b86b' : '#7be2c4'} stroke="#112f39" strokeWidth="3" />
              <text y={index === 0 ? -37 : 44} textAnchor="middle" fill="#e4f4ef" fontSize="11" fontWeight="700">{project.utility_id}</text>
            </g>
          ))}
          <text x="348" y="432" textAnchor="middle" fill="#8ab1b7" fontSize="9" letterSpacing="2">LONGITUDE / LATITUDE PLOT</text>
        </svg>
      </div>
      <div className="map-footer"><span className="legend-dot" style={{ background: hasReference ? '#f4b86b' : '#7be2c4' }} /> {!hasGeometry ? 'No project geometry loaded' : hasReference ? 'Reference locations' : 'Project geometry'} <span className="map-footer-note">{!hasGeometry ? 'Waiting for API records' : hasReference ? 'Site geometry needs review' : 'Source-backed geometry'}</span></div>
    </div>
  )
}
