import type { PairAssessment, Project, ReviewQueue } from '../src/types'

// Source-backed records from Badri/output/asus_project_versions. The points
// are reference locations and remain explicitly unresolved in this preview.
export const previewProjects: Project[] = [
  {
    project_id: 'DESC-WINNSBORO-WEST-2025-208-E', utility_id: 'DESC',
    project_name: 'Winnsboro West 230/115 kV Substation', project_type: 'substation',
    status: 'in_progress', location_text: 'Winnsboro West, Fairfield County, South Carolina; exact substation parcel requires georeferencing from DESC Exhibit B',
    geometry: { type: 'Point', coordinates: [-81.088056, 34.376944] },
    geometry_origin: 'CENTER_POINT', geometry_quality: 'UNRESOLVED', validation_state: 'NEEDS_REVIEW',
    version_id: 'PREVIEW-DESC', version_number: 0, is_fixture: false, schedule: { type: 'UNKNOWN' },
    evidence: [
      { source_id: 'SCPSC-2025-208-E-2026-08-14', source_name: 'DESC quarterly update, SCPSC Docket 2025-208-E', source_url: 'https://dms.psc.sc.gov/Attachments/Matter/72042102-313d-484f-b112-50ba66742d92', page_or_row: 'page 1', snippet: 'Clearing and grading started; projected completion January 1, 2028.' },
      { source_id: 'SCPSC-2025-208-E-EXHIBIT-B', source_name: 'DESC Exhibits A and B', source_url: 'https://dms.psc.sc.gov/Attachments/Matter/bed0f283-a5b8-4c56-9c36-202d635a503c', page_or_row: 'page 3, Exhibit B', snippet: 'Map depicts Winnsboro West; current coordinate is the town reference point.' },
    ],
  },
  {
    project_id: 'GPC-BIG-OGEECHEE-500-230-2026', utility_id: 'GPC',
    project_name: 'Big Ogeechee 500/230 kV Substation', project_type: 'substation',
    status: 'unknown', location_text: 'West Chatham County, Georgia, near Little Ogeechee Substation; exact Big Ogeechee site requires confirmation',
    geometry: { type: 'Point', coordinates: [-81.25315, 32.00679] },
    geometry_origin: 'CENTER_POINT', geometry_quality: 'UNRESOLVED', validation_state: 'NEEDS_REVIEW',
    version_id: 'PREVIEW-GPC', version_number: 0, is_fixture: false, schedule: { type: 'UNKNOWN' },
    evidence: [
      { source_id: 'GPC-BIG-OGEECHEE-2026-06-17', source_name: 'Georgia Power Big Ogeechee project update', source_url: 'https://www.georgiapower.com/news-hub/community/big-ogeechee-substation-power-savannah-area-growth-storm-hardened-coastal-grid.html', snippet: 'Describes Big Ogeechee in west Chatham County; current service status still needs confirmation.' },
      { source_id: 'OSM-GPC-savannah', source_name: 'OpenStreetMap Little Ogeechee Substation', source_url: 'https://www.openstreetmap.org/way/121701191', page_or_row: 'way 121701191', snippet: 'Reference point locates nearby Little Ogeechee, not the Big Ogeechee project site.' },
    ],
  },
]

export const previewQueue: ReviewQueue = {
  total: 2,
  projects: previewProjects.map(project => ({
    project, qualified_ready: false, matching_eligible: false, coordinate_role: 'REFERENCE_ONLY',
    blockers: project.utility_id === 'GPC'
      ? ['UNRESOLVED_GEOMETRY', 'REFERENCE_CENTER_POINT', 'VALIDATION_PENDING', 'STATUS_NOT_ELIGIBLE']
      : ['UNRESOLVED_GEOMETRY', 'REFERENCE_CENTER_POINT', 'VALIDATION_PENDING'],
  })),
}

function haversine(a: [number, number], b: [number, number]): number {
  const [lon1, lat1, lon2, lat2] = [...a, ...b].map(x => x * Math.PI / 180)
  const h = Math.sin((lat2 - lat1) / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin((lon2 - lon1) / 2) ** 2
  return 2 * 6371008.8 * Math.asin(Math.sqrt(h))
}

export function previewAssessment(a: Project, b: Project): PairAssessment {
  const meters = a.geometry?.type === 'Point' && b.geometry?.type === 'Point'
    ? haversine(a.geometry.coordinates, b.geometry.coordinates) : null
  const rowA = previewQueue.projects.find(row => row.project.project_id === a.project_id)
  const rowB = previewQueue.projects.find(row => row.project.project_id === b.project_id)
  return {
    project_a: { project_id: a.project_id, blockers: rowA?.blockers ?? [], coordinate_role: rowA?.coordinate_role ?? 'NONE', qualified_ready: false },
    project_b: { project_id: b.project_id, blockers: rowB?.blockers ?? [], coordinate_role: rowB?.coordinate_role ?? 'NONE', qualified_ready: false },
    distance: meters === null ? null : { meters, miles: meters / 1609.344, kind: 'REFERENCE_POINT_SEPARATION', within_configured_maximum: meters < 40000 },
    maximum_meters: 40000, blockers: ['PROJECT_A_NEEDS_REVIEW', 'PROJECT_B_NEEDS_REVIEW'], qualifies: false,
  }
}
