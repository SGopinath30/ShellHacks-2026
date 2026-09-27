"""Read-only, fixed-host SAGIS parcel lookup. Results are candidates, never matches."""
import re
import httpx

SAGIS = 'https://services.sagis.org/arcgis/rest/services/SAGISorg/SAGISorgMapLayers/MapServer/124'


def parcel_candidates(project):
    if project['project_id'] != 'GPC-BIG-OGEECHEE-500-230-2026':
        return {'state': 'NOT_CONFIGURED', 'note': 'No county GIS adapter for this project; use official project sources.'}
    try:
        with httpx.Client(timeout=10, follow_redirects=False) as client:
            metadata = client.get(SAGIS, params={'f': 'json'}); metadata.raise_for_status()
            fields = metadata.json().get('fields', [])
            owner = next(field['name'] for field in fields if 'owner' in field.get('name', '').lower()
                         and field.get('type') == 'esriFieldTypeString')
            if not re.fullmatch(r'[a-zA-Z_][a-zA-Z0-9_]*', owner):
                raise ValueError('Unexpected owner field')
            params = {'f': 'geojson', 'where': f"UPPER({owner}) LIKE '%GEORGIA POWER%'",
                      'outFields': '*', 'outSR': 4326, 'returnGeometry': 'true',
                      'resultRecordCount': 5, 'geometryPrecision': 6,
                      'geometry': '-81.65,31.85,-81.05,32.25', 'geometryType': 'esriGeometryEnvelope',
                      'inSR': 4326, 'spatialRel': 'esriSpatialRelIntersects'}
            response = client.get(SAGIS + '/query', params=params); response.raise_for_status()
            if len(response.content) > 500000:
                raise ValueError('GIS response exceeds research budget')
            data = response.json()
            if data.get('type') != 'FeatureCollection':
                raise ValueError('GIS did not return GeoJSON')
            return {'state': 'CANDIDATES', 'source_url': str(response.url), 'crs': 'EPSG:4326',
                    'note': 'At most five owner-matched parcels in a discovery envelope; not exhaustive. Ownership does not identify Big Ogeechee. Never substitute a parcel centroid for site geometry.',
                    'features': data.get('features', [])[:5]}
    except (httpx.HTTPError, ValueError, StopIteration, KeyError, TypeError):
        return {'state': 'UNAVAILABLE', 'source_url': SAGIS,
                'note': 'County GIS lookup unavailable or schema changed. Do not infer coordinates; request a project-specific parcel/site map.'}
