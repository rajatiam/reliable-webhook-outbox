import hashlib, io, json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from tests.helpers import AuthorizedClient as TestClient
import app, api

EXAMPLE = json.loads((Path(__file__).parent/'project.json').read_text(encoding='utf-8'))['example']
ACTION = 'deliver'
EXPECTED = {'status': 'delivered', 'attempts': 1}
INVALID = {'payload': 'broken'}

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); app.DB=Path(self.tmp.name)/'test.db'; self.client=TestClient(api.app)
    def tearDown(self): self.client.close(); self.tmp.cleanup()
    def test_persistence_and_summary(self):
        row=app.create(dict(EXAMPLE)); self.assertEqual(app.records()[0]['id'],row['id']); self.assertIsInstance(app.summary(app.records()),dict)
    def test_missing_field_rejected(self):
        example=dict(EXAMPLE); example.pop(next(iter(example)))
        with self.assertRaises(ValueError): app.create(example)
    def test_domain_invalid_value(self):
        with self.assertRaises(ValueError): app.create(dict(EXAMPLE,**INVALID))
    def test_workflow(self):
        row=app.create(dict(EXAMPLE))
        with patch('backend.domain.urlopen') as request:
            request.return_value.__enter__.return_value.status=200
            result=app.action(row['id'],ACTION)
        for key,value in EXPECTED.items(): self.assertEqual(result[key],value)
        self.assertEqual(app.summary(app.records())['delivered'],1)
    def test_http_roundtrip(self):
        self.assertEqual(self.client.get('/health').status_code,200)
        response=self.client.post('/api/records',json=EXAMPLE); self.assertEqual(response.status_code,201); row=response.json()
        self.assertEqual(len(self.client.get('/api/records').json()),1)
        self.assertTrue(self.client.delete('/api/records/'+str(row['id'])).json()['deleted'])
        self.assertEqual(self.client.delete('/api/records/'+str(row['id'])).status_code,404)
    def test_transport_and_unknown_action(self):
        self.assertEqual(self.client.post('/api/records',json=[]).status_code,422)
        row=app.create(dict(EXAMPLE))
        self.assertEqual(self.client.post(f"/api/records/{row['id']}/unsupported").status_code,400)
    def test_metrics_openapi_and_routes(self):
        row=app.create(dict(EXAMPLE)); self.assertIn('portfolio_records 1',self.client.get('/metrics').text)
        self.assertIn('/api/records',self.client.get('/openapi.json').json()['paths'])
        if app.CONFIG['kind']=='links':
            result=self.client.get('/r/'+row['slug'],follow_redirects=False); self.assertEqual(result.status_code,302); self.assertEqual(app.records()[0]['visits'],1)
        if app.CONFIG['kind']=='artifacts':
            payload=self.client.get(f"/api/artifacts/{row['id']}/download").content
            self.assertEqual(hashlib.sha256(payload).hexdigest(),row['sha256'])
        if app.CONFIG['kind']=='webhooks': self.assertTrue(self.client.post('/api/receiver',json={'test':1}).json()['accepted'])
    def test_boundaries(self):
        kind=app.CONFIG['kind']; row=app.create(dict(EXAMPLE))
        if kind in ['expenses','flags','links','artifacts']:
            with self.assertRaises(ValueError): app.create(dict(EXAMPLE))
        elif kind=='incidents':
            with self.assertRaises(ValueError): app.action(row['id'],'resolve')
        elif kind=='crm':
            for _ in range(3): app.action(row['id'],'advance')
            with self.assertRaises(ValueError): app.action(row['id'],'advance')
        elif kind=='quality':
            app.action(row['id'],'profile'); self.assertEqual(app.records()[0]['findings'][0]['line'],3)
        elif kind=='canary':
            bad=app.create(dict(EXAMPLE,errors=20)); self.assertEqual(app.action(bad['id'],'analyze')['decision'],'rollback')
        elif kind=='planner':
            with self.assertRaises(ValueError): app.create(dict(EXAMPLE,graph='{"api":["missing"]}'))
        elif kind=='webhooks':
            with patch('backend.domain.urlopen',side_effect=OSError('target unavailable')):
                self.assertEqual(app.action(row['id'],'deliver')['status'],'failed')

if __name__=='__main__': unittest.main()
