import type { Geometry, Project } from './types'

const SOUTHEAST_BOUNDS = { west: -90, south: 24, east: -75, north: 38 }

const SOURCE_BACKED_REFERENCES: Record<string, { coordinates: [number, number]; location: string }> = {
  'DESC-WINNSBORO-WEST-2025-208-E': {
    coordinates: [-81.088056, 34.376944],
    location: 'Winnsboro, Fairfield County, South Carolina · town reference only',
  },
}

function coordinateIsInSoutheast(coordinate: number[]): boolean {
  const [longitude, latitude] = coordinate
  return Number.isFinite(longitude) && Number.isFinite(latitude)
    && longitude >= SOUTHEAST_BOUNDS.west && longitude <= SOUTHEAST_BOUNDS.east
    && latitude >= SOUTHEAST_BOUNDS.south && latitude <= SOUTHEAST_BOUNDS.north
}

export function geometryIsInSoutheast(geometry: Project['geometry']): boolean {
  if (!geometry) return false
  if (geometry.type === 'Point') return coordinateIsInSoutheast(geometry.coordinates)
  return geometry.coordinates.length > 0 && geometry.coordinates.every(coordinate => coordinateIsInSoutheast(coordinate))
}

export function usesSourceBackedReference(project: Project): boolean {
  return Boolean(SOURCE_BACKED_REFERENCES[project.project_id]
    && (!project.geometry || !geometryIsInSoutheast(project.geometry)))
}

export function mapGeometry(project: Project): Geometry | null {
  if (project.geometry && geometryIsInSoutheast(project.geometry)) return project.geometry
  const reference = SOURCE_BACKED_REFERENCES[project.project_id]
  return reference ? { type: 'Point', coordinates: reference.coordinates } : null
}

export function mapLocation(project: Project): string {
  return usesSourceBackedReference(project)
    ? SOURCE_BACKED_REFERENCES[project.project_id].location
    : project.location_text
}

function representativePoint(geometry: Geometry): [number, number] {
  if (geometry.type === 'Point') return geometry.coordinates
  const middle = geometry.coordinates[Math.floor(geometry.coordinates.length / 2)]
  return middle
}

export function referenceDistanceMeters(first: Project, second: Project): number | null {
  const firstGeometry = mapGeometry(first)
  const secondGeometry = mapGeometry(second)
  if (!firstGeometry || !secondGeometry) return null
  const [firstLongitude, firstLatitude] = representativePoint(firstGeometry)
  const [secondLongitude, secondLatitude] = representativePoint(secondGeometry)
  const latitudeDelta = (secondLatitude - firstLatitude) * Math.PI / 180
  const longitudeDelta = (secondLongitude - firstLongitude) * Math.PI / 180
  const firstLatitudeRadians = firstLatitude * Math.PI / 180
  const secondLatitudeRadians = secondLatitude * Math.PI / 180
  const haversine = Math.sin(latitudeDelta / 2) ** 2
    + Math.cos(firstLatitudeRadians) * Math.cos(secondLatitudeRadians) * Math.sin(longitudeDelta / 2) ** 2
  return 6_371_008.8 * 2 * Math.asin(Math.sqrt(haversine))
}
