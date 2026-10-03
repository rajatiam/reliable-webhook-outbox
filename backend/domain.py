import csv, hashlib, io, json, math, re
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from .validation import validate_input, http_url, unique

def now(): return datetime.now(timezone.utc).isoformat()
def validate(data,records): return initialize(validate_input(data,CONFIG['example']),records)

def initialize(row,records):
    http_url(row['target'])
    try: payload=json.loads(row['payload'])
    except ValueError: raise ValueError('Payload must be valid JSON')
    if not isinstance(payload,dict): raise ValueError('Payload must be a JSON object')
    return dict(row,status='queued',attempts=0,last_error=None,response_status=None,delivery_id=__import__('uuid').uuid4().hex)
def summary(rows): return {'deliveries':len(rows),'delivered':sum(r['status']=='delivered' for r in rows),'failed':sum(r['status']=='failed' for r in rows),'attempts':sum(r['attempts'] for r in rows)}
def transition(row,action):
    if action!='deliver' or row['status']=='delivered': raise ValueError('Only queued or failed deliveries can be delivered')
    row=dict(row,attempts=row['attempts']+1)
    try:
        request=Request(row['target'],data=row['payload'].encode(),headers={'Content-Type':'application/json','X-Delivery-ID':row.get('delivery_id',str(row['id']))},method='POST')
        with urlopen(request,timeout=3) as response: row.update(status='delivered',response_status=response.status,last_error=None)
    except Exception as exc: row.update(status='failed',last_error=str(exc),response_status=None)
    return row
