from datetime import datetime, timezone
from uuid import uuid4
from copy import deepcopy

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.main import app
from app.challenge import research
from app.challenge.location_workbench import readiness
from tests.test_location_workbench import sourced


def proposal():
    return {'summary': 'Source-backed candidate for human review', 'missing_evidence': [], 'outreach_draft': '',
            'verification': {'base_version_id': 'PV-old', 'actor_id': 'AI', 'actor_role': 'AI',
                'reason': 'Candidate site', 'location_text': 'Test project site',
                'geometry': {'type': 'Point', 'coordinates': [-81.2, 32]},
                'geometry_origin': 'PUBLIC_GIS', 'geometry_quality': 'HIGH',
                'geometry_evidence': {'source_id': '42', 'source_name': 'GIS',
                    'source_url': 'https://example.com/42', 'page_or_row': 'feature 42'}}}


@pytest.fixture
def row():
    return {'proposal_id': uuid4(), 'project_id': 'project', 'base_version_id': 'PV-old',
            'revision': 1, 'state': 'REVIEW', 'payload': proposal(), 'research': {}, 'error': None,
            'created_at': datetime.now(timezone.utc), 'updated_at': datetime.now(timezone.utc)}


class FakeConnection:
    def __init__(self, row): self.row = row; self.calls = []; self.rollback = False
    def __enter__(self): return self
    def __exit__(self, typ, *args): self.rollback = typ is not None
    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        if 'SET state=%s' in sql: self.row['state'] = params[0]
        if 'SET payload=%s' in sql:
            self.row['payload'] = params[0].obj
            self.row['revision'] += 1
        return self
    def fetchone(self): return self.row


def request(row, **kwargs):
    return research.Review(proposal_hash=research.digest(row), actor_id='human-reviewer',
        reason='Checked the feature and source document', action='APPROVE', evidence_confirmed=True, **kwargs)


def test_research_routes_fail_closed_without_configured_key(monkeypatch):
    monkeypatch.delenv('WRITE_API_KEY', raising=False)
    client = TestClient(app)
    assert client.get('/api/v1/projects/example/research').status_code == 503
    assert client.post('/api/v1/projects/example/research').status_code == 503
    monkeypatch.setenv('WRITE_API_KEY', 'review-secret')
    assert client.get('/api/v1/projects/example/research').status_code == 401
    assert client.post('/api/v1/projects/example/research').status_code == 401
    assert client.post(f'/api/v1/research/{uuid4()}/review', json={}).status_code == 401


@pytest.mark.parametrize('change', ['missing_attestation', 'missing_geometry', 'missing_evidence', 'stale_hash', 'already_applied'])
def test_approval_guards_never_write(monkeypatch, row, change):
    req = request(row)
    if change == 'missing_attestation': req.evidence_confirmed = False
    if change == 'missing_geometry': row['payload']['verification'] = None
    if change == 'missing_evidence': row['payload']['missing_evidence'] = ['Need current status']
    if change == 'already_applied': row['state'] = 'APPLIED'
    if change != 'stale_hash': req.proposal_hash = research.digest(row)
    else: row['revision'] += 1
    conn = FakeConnection(row)
    monkeypatch.setattr(research.repository, 'connect', lambda: conn)
    monkeypatch.setattr(research, 'verify_location_in_transaction', lambda *args: pytest.fail('Must not write'))
    with pytest.raises(HTTPException): research.decide(row['proposal_id'], req)
    assert conn.rollback


def test_approval_uses_human_identity_and_same_transaction(monkeypatch, row):
    conn = FakeConnection(row)
    monkeypatch.setattr(research.repository, 'connect', lambda: conn)
    def verify(connection, project_id, values):
        assert connection is conn
        assert values.actor_id == 'human-reviewer'
        assert values.actor_role == 'Location Reviewer'
        assert values.base_version_id == 'PV-old'
        return {'project': {'version_id': 'PV-new'}}
    monkeypatch.setattr(research, 'verify_location_in_transaction', verify)
    result = research.decide(row['proposal_id'], request(row))
    assert result['proposal']['state'] == 'APPLIED'
    assert any('research_reviews' in sql for sql, _ in conn.calls)
    assert not conn.rollback


def test_stale_project_aborts_approval(monkeypatch, row):
    conn = FakeConnection(row)
    monkeypatch.setattr(research.repository, 'connect', lambda: conn)
    def stale(*args): raise ValueError('Project version changed; refresh before verifying')
    monkeypatch.setattr(research, 'verify_location_in_transaction', stale)
    with pytest.raises(ValueError, match='Project version changed'): research.decide(row['proposal_id'], request(row))
    assert conn.rollback
    assert row['state'] == 'REVIEW'
    assert not any('research_reviews' in sql for sql, _ in conn.calls)


def test_rejection_does_not_verify(monkeypatch, row):
    conn = FakeConnection(row)
    monkeypatch.setattr(research.repository, 'connect', lambda: conn)
    monkeypatch.setattr(research, 'verify_location_in_transaction', lambda *args: pytest.fail('Must not write'))
    req = request(row); req.action = 'REJECT'
    assert research.decide(row['proposal_id'], req)['proposal']['state'] == 'REJECTED'


def test_edit_invalidates_approval_hash_and_preserves_base(monkeypatch, row):
    conn = FakeConnection(row)
    monkeypatch.setattr(research.repository, 'connect', lambda: conn)
    old_hash = research.digest(row)
    payload = deepcopy(row['payload']); payload['summary'] = 'Corrected source interpretation'
    req = research.Revision(proposal_hash=old_hash, actor_id='human', reason='Corrected source', proposal=payload)
    result = research.revise(row['proposal_id'], req)
    assert result['proposal_hash'] != old_hash
    assert result['revision'] == 2
    assert sum('INSERT INTO synchro.research_reviews' in sql for sql, _ in conn.calls) == 2


@pytest.mark.parametrize('status', ['completed', 'operational'])
def test_completed_sites_are_recordable_but_not_eligible(status):
    project = sourced('GPC-BIG-OGEECHEE-500-230-2026.json', 'PV-old')
    project = type(project).model_validate({**project.model_dump(mode='json'), 'status': status})
    assert 'STATUS_NOT_ELIGIBLE' in readiness(project)['blockers']
    draft = proposal()['verification']
    draft['status'] = status
    assert research.DraftVerification.model_validate(draft).status == status


def test_research_failure_is_saved_without_leaking_provider_error(monkeypatch, row):
    conn = FakeConnection(row)
    monkeypatch.setattr(research.repository, 'connect', lambda: conn)
    def fail(*args): raise RuntimeError('SECRET provider URL')
    monkeypatch.setattr(research, 'generate', fail)
    research.run(row['proposal_id'], {})
    assert 'FAILED' in conn.calls[0][0]
    assert 'SECRET' not in str(conn.calls)


def test_provider_uses_grounded_research_then_validated_extraction(monkeypatch):
    import json
    import httpx
    monkeypatch.setenv('GEMINI_API_KEY', 'provider-secret')
    monkeypatch.setattr(research, 'parcel_candidates', lambda p: {'state': 'UNAVAILABLE'})
    calls = []
    def respond(req):
        body = json.loads(req.content); calls.append(body)
        if len(calls) == 1:
            data = {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': 'No exact coordinates found.'}]},
                    'groundingMetadata': {'groundingChunks': [{'web': {'uri': 'https://example.com/source', 'title': 'Source'}}]}}]}
        else:
            data = {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': json.dumps({
                'summary': 'Unresolved', 'missing_evidence': ['Need site geometry'], 'outreach_draft': 'Please confirm site.', 'verification': None})}]}}]}
        return httpx.Response(200, json=data)
    client = httpx.Client(transport=httpx.MockTransport(respond))
    monkeypatch.setattr(research.httpx, 'Client', lambda **kwargs: client)
    payload, provenance = research.generate({'project_id': 'test', 'version_id': 'PV-old'})
    assert payload['verification'] is None
    assert provenance['grounding']['groundingChunks']
    assert len(calls) == 2
    assert calls[0]['tools'] == [{'google_search': {}}, {'url_context': {}}]
    assert 'tools' not in calls[1]
    assert 'provider-secret' not in json.dumps(calls)


def test_search_quota_falls_back_to_existing_source_urls(monkeypatch):
    import json
    import httpx
    monkeypatch.setenv('GEMINI_API_KEY', 'provider-secret')
    monkeypatch.setattr(research, 'parcel_candidates', lambda p: {'state': 'UNAVAILABLE'})
    calls = []

    def respond(req):
        body = json.loads(req.content); calls.append(body)
        if len(calls) == 1:
            return httpx.Response(429, json={'error': {'status': 'RESOURCE_EXHAUSTED'}})
        if len(calls) == 2:
            return httpx.Response(200, json={'candidates': [{
                'finishReason': 'STOP',
                'content': {'parts': [{'text': 'Reviewed the supplied official source URL.'}]},
                'groundingMetadata': {'groundingChunks': [{'web': {
                    'uri': 'https://example.com/source', 'title': 'Source'}}]}}]})
        return httpx.Response(200, json={'candidates': [{
            'finishReason': 'STOP', 'content': {'parts': [{'text': json.dumps({
                'summary': 'Limited source review',
                'missing_evidence': ['Broader source discovery remains needed'],
                'outreach_draft': '', 'verification': None})}]}}]})

    client = httpx.Client(transport=httpx.MockTransport(respond))
    monkeypatch.setattr(research.httpx, 'Client', lambda **kwargs: client)
    payload, provenance = research.generate({
        'project_id': 'test', 'version_id': 'PV-old',
        'evidence': [{'source_url': 'https://example.com/source'}]})

    assert payload['verification'] is None
    assert len(calls) == 3
    assert calls[0]['tools'] == [{'google_search': {}}, {'url_context': {}}]
    assert calls[1]['tools'] == [{'url_context': {}}]
    assert 'source discovery was limited' in calls[1]['contents'][0]['parts'][0]['text']
    assert provenance['retrieval_mode'] == 'URL_CONTEXT_ONLY_QUOTA_FALLBACK'


def test_gis_unavailable_never_invents_coordinates(monkeypatch):
    import httpx
    from app.challenge import research_gis
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(503)))
    monkeypatch.setattr(research_gis.httpx, 'Client', lambda **kwargs: client)
    result = research_gis.parcel_candidates({'project_id': 'GPC-BIG-OGEECHEE-500-230-2026'})
    assert result['state'] == 'UNAVAILABLE'
    assert 'features' not in result


def test_real_database_research_approval_and_stale_version(monkeypatch):
    """Opt-in isolated database only; never runs against the deployed database."""
    import os
    from psycopg.types.json import Jsonb
    from app.challenge.contracts import ProjectInput
    if os.getenv('RESEARCH_TEST_DATABASE') != '1':
        pytest.skip('Set RESEARCH_TEST_DATABASE=1 with an isolated DATABASE_URL')
    monkeypatch.setenv('WRITE_API_KEY', 'test-reviewer')
    monkeypatch.setenv('GEMINI_API_KEY', 'mock-provider')
    research.repository.migrate()
    research.repository.migrate()  # additive/idempotent migration
    original = sourced('GPC-BIG-OGEECHEE-500-230-2026.json', 'unused')
    record = original.model_dump(mode='json', exclude={'version_id', 'version_number'})
    record['project_id'] = 'research-test-' + str(uuid4())
    project = research.repository.save(ProjectInput.model_validate(record))
    def generate(p):
        payload = proposal()
        payload['verification']['base_version_id'] = p['version_id']
        return payload, {'model': 'mock', 'report': 'Test only'}
    monkeypatch.setattr(research, 'generate', generate)
    client = TestClient(app)
    headers = {'X-API-Key': 'test-reviewer'}
    path = f'/api/v1/projects/{project.project_id}/research'
    assert client.post(path, headers=headers).status_code == 202
    row = client.get(path, headers=headers).json()[0]
    assert row['state'] == 'REVIEW'
    with research.repository.connect() as conn:
        assert research.repository.current_project(conn, project.project_id).version_id == project.version_id
    request_body = {'proposal_hash': row['proposal_hash'], 'actor_id': 'human', 'reason': 'Checked sources',
                    'action': 'APPROVE', 'evidence_confirmed': True}
    result = client.post(f"/api/v1/research/{row['proposal_id']}/review", headers=headers, json=request_body)
    assert result.status_code == 200, result.text
    updated = result.json()['verification']['project']
    assert updated['version_id'] != project.version_id
    assert client.post(f"/api/v1/research/{row['proposal_id']}/review", headers=headers, json=request_body).status_code == 409
    with research.repository.connect() as conn:
        assert conn.execute('SELECT count(*) AS n FROM synchro.research_reviews WHERE proposal_id=%s', (row['proposal_id'],)).fetchone()['n'] == 1
        with pytest.raises(Exception, match='append-only'):
            conn.execute('DELETE FROM synchro.research_reviews WHERE proposal_id=%s', (row['proposal_id'],))
    # A newer manual project version makes a saved proposal stale.
    assert client.post(path, headers=headers).status_code == 202
    stale = client.get(path, headers=headers).json()[0]
    current = {k: v for k, v in updated.items() if k not in ('version_id', 'version_number')}
    current['location_text'] = 'Updated while research was under review'
    research.repository.save(ProjectInput.model_validate(current))
    request_body['proposal_hash'] = stale['proposal_hash']
    result = client.post(f"/api/v1/research/{stale['proposal_id']}/review", headers=headers, json=request_body)
    assert result.status_code == 409
    assert client.get(path, headers=headers).json()[0]['state'] == 'REVIEW'
