import { useEffect, useMemo, useRef } from 'react'
import { AttributionControl, LngLatBounds, Map as MapLibreMap, NavigationControl, Popup, type GeoJSONSource, type MapMouseEvent } from 'maplibre-gl'
import type { Feature, FeatureCollection, Geometry as GeoJSONGeometry } from 'geojson'
import { MapPin, Maximize2 } from 'lucide-react'
import type { Project } from './types'

type ProjectProperties = {
  projectId: string
  projectName: string
  utilityId: string
  status: string
  location: string
  quality: string
  origin: string
  validation: string
}

const EMPTY_FEATURES: FeatureCollection<GeoJSONGeometry, ProjectProperties> = { type: 'FeatureCollection', features: [] }
const MAP_STYLE = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json'

function projectFeatures(projects: Project[]): FeatureCollection<GeoJSONGeometry, ProjectProperties> {
  const features: Feature<GeoJSONGeometry, ProjectProperties>[] = []
  for (const project of projects) {
    if (!project.geometry) continue
    features.push({
      type: 'Feature',
      id: project.project_id,
      geometry: project.geometry,
      properties: {
        projectId: project.project_id,
        projectName: project.project_name,
        utilityId: project.utility_id,
        status: project.status,
        location: project.location_text,
        quality: project.geometry_quality,
        origin: project.geometry_origin,
        validation: project.validation_state,
      },
    })
  }
  return { type: 'FeatureCollection', features }
}

export default function MapPanel({ projects, compact = false }: { projects: Project[]; compact?: boolean }) {
  const mapHost = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MapLibreMap | null>(null)
  const geojson = useMemo(() => projectFeatures(projects), [projects])
  const hasReference = projects.some(project => project.geometry_origin === 'CENTER_POINT' || project.geometry_quality === 'UNRESOLVED')
  const hasGeometry = geojson.features.length > 0

  useEffect(() => {
    if (!mapHost.current) return
    const map = new MapLibreMap({
      container: mapHost.current,
      style: MAP_STYLE,
      center: [-81.4, 32.25],
      zoom: 6.1,
      minZoom: 3,
      maxZoom: 15,
      attributionControl: false,
      cooperativeGestures: true,
      pitch: 35,
      bearing: -8,
    })
    mapRef.current = map
    map.addControl(new NavigationControl({ showCompass: true, visualizePitch: true }), 'top-right')
    map.addControl(new AttributionControl({ compact: true }), 'bottom-right')

    map.once('load', () => {
      if (!map.getSource('synchro-projects')) {
        map.addSource('synchro-projects', { type: 'geojson', data: EMPTY_FEATURES, promoteId: 'projectId' })
        map.addLayer({
          id: 'project-lines-casing', type: 'line', source: 'synchro-projects',
          filter: ['==', ['geometry-type'], 'LineString'],
          paint: { 'line-color': '#061a21', 'line-width': 8, 'line-opacity': 0.9, 'line-blur': 1 },
        })
        map.addLayer({
          id: 'project-lines', type: 'line', source: 'synchro-projects',
          filter: ['==', ['geometry-type'], 'LineString'],
          paint: {
            'line-color': ['case', ['==', ['get', 'quality'], 'UNRESOLVED'], '#f1b96e', '#72e3be'],
            'line-width': ['interpolate', ['linear'], ['zoom'], 3, 2.5, 10, 5],
            'line-opacity': 0.94,
            'line-dasharray': ['case', ['==', ['get', 'quality'], 'APPROXIMATE'], ['literal', [2, 1.5]], ['literal', [1, 0]]],
          },
        })
        map.addLayer({
          id: 'project-points-halo', type: 'circle', source: 'synchro-projects',
          filter: ['==', ['geometry-type'], 'Point'],
          paint: {
            'circle-radius': ['interpolate', ['linear'], ['zoom'], 3, 9, 10, 16],
            'circle-color': ['case', ['==', ['get', 'quality'], 'UNRESOLVED'], '#f1b96e', '#72e3be'],
            'circle-opacity': 0.18,
            'circle-blur': 0.7,
          },
        })
        map.addLayer({
          id: 'project-points', type: 'circle', source: 'synchro-projects',
          filter: ['==', ['geometry-type'], 'Point'],
          paint: {
            'circle-radius': ['interpolate', ['linear'], ['zoom'], 3, 3.5, 10, 6],
            'circle-color': ['case', ['==', ['get', 'quality'], 'UNRESOLVED'], '#f1b96e', '#72e3be'],
            'circle-stroke-color': '#eafff6', 'circle-stroke-width': 1.5, 'circle-opacity': 0.98,
          },
        })
        map.addLayer({
          id: 'project-labels', type: 'symbol', source: 'synchro-projects',
          layout: {
            'text-field': ['get', 'utilityId'], 'text-font': ['Open Sans Semibold', 'Arial Unicode MS Bold'],
            'text-size': 11, 'text-offset': [0, 1.45], 'text-anchor': 'top', 'text-allow-overlap': false,
          },
          paint: { 'text-color': '#e8fff5', 'text-halo-color': '#09232b', 'text-halo-width': 1.5 },
        })
      }
        const source = map.getSource('synchro-projects') as GeoJSONSource | undefined
      source?.setData(geojson)
      if (geojson.features.length) {
        const bounds = new LngLatBounds()
        for (const feature of geojson.features) {
          const geometry = feature.geometry
          if (geometry.type === 'Point') bounds.extend(geometry.coordinates as [number, number])
          else if (geometry.type === 'LineString') geometry.coordinates.forEach(coordinate => bounds.extend(coordinate as [number, number]))
        }
        if (!bounds.isEmpty()) map.fitBounds(bounds, { padding: compact ? 54 : 76, maxZoom: 9.5, duration: 900 })
      }
    })

    const showProject = (event: MapMouseEvent) => {
      const feature = map.queryRenderedFeatures(event.point, { layers: ['project-points', 'project-lines'] })[0]
      if (!feature) return
      const properties = feature.properties as ProjectProperties
      new Popup({ closeButton: false, offset: 12, className: 'synchro-map-popup' })
        .setLngLat(event.lngLat)
        .setHTML(`<strong>${escapeHtml(properties.projectName)}</strong><span>${escapeHtml(properties.utilityId)} · ${escapeHtml(properties.status.replaceAll('_', ' '))}</span><small>${escapeHtml(properties.location)} · ${escapeHtml(properties.quality)} geometry</small>`)
        .addTo(map)
    }
    map.on('click', showProject)
    map.on('mouseenter', 'project-points', () => { map.getCanvas().style.cursor = 'pointer' })
    map.on('mouseleave', 'project-points', () => { map.getCanvas().style.cursor = '' })
    map.on('mouseenter', 'project-lines', () => { map.getCanvas().style.cursor = 'pointer' })
    map.on('mouseleave', 'project-lines', () => { map.getCanvas().style.cursor = '' })

    const observer = new ResizeObserver(() => map.resize())
    observer.observe(mapHost.current)
    return () => {
      observer.disconnect()
      map.remove()
      mapRef.current = null
    }
  }, [compact])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    const update = () => {
      const source = map.getSource('synchro-projects') as GeoJSONSource | undefined
      source?.setData(geojson)
      if (geojson.features.length) {
        const bounds = new LngLatBounds()
        for (const feature of geojson.features) {
          const geometry = feature.geometry
          if (geometry.type === 'Point') bounds.extend(geometry.coordinates as [number, number])
          else if (geometry.type === 'LineString') geometry.coordinates.forEach(coordinate => bounds.extend(coordinate as [number, number]))
        }
        if (!bounds.isEmpty()) map.fitBounds(bounds, { padding: compact ? 54 : 76, maxZoom: 9.5, duration: 700 })
      }
    }
    if (map.isStyleLoaded()) update()
    else map.once('load', update)
  }, [geojson, compact])

  return (
    <div className={`map-panel ${compact ? 'map-panel-compact' : ''}`}>
      <div className="map-topline">
        <div className="map-topline-title"><MapPin size={15} /> Regional project map</div>
        <span className="map-scale"><Maximize2 size={13} /> Live geometry</span>
      </div>
      <div className="map-canvas maplibre-canvas" ref={mapHost} role="img" aria-label="Interactive map of current project locations" />
      <div className="map-footer"><span className="legend-dot" style={{ background: hasReference ? '#f1b96e' : '#72e3be' }} /> {!hasGeometry ? 'No project geometry loaded' : hasReference ? 'Reference or unresolved location' : 'Source-backed project geometry'} <span className="map-footer-note">{!hasGeometry ? 'Waiting for API records' : hasReference ? 'Location requires review' : 'Click a feature for details'}</span></div>
    </div>
  )
}

function escapeHtml(value: string) {
  return value.replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character]!)
}
