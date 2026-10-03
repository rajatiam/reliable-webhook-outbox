import csv, hashlib, io, json, math, re
from datetime import datetime, timezone
from urllib.parse import urlparse
from urllib.request import Request, urlopen

def now(): return datetime.now(timezone.utc).isoformat()

def validate(data, records):
    if not isinstance(data,dict): raise ValueError('JSON object required')
    row = {}
    for key,example in CONFIG['example'].items():
        value = data.get(key)
        if isinstance(example,bool):
            if not isinstance(value,bool): raise ValueError(key+' must be boolean')
        elif isinstance(example,(int,float)):
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value < 0: raise ValueError(key+' must be finite and nonnegative')
            if isinstance(example,int) and not isinstance(value,int): raise ValueError(key+' must be an integer')
        elif not isinstance(value,str) or not value.strip() or len(value)>2000: raise ValueError(key+' requires text, up to 2000 characters')
        row[key] = value.strip() if isinstance(value,str) else value
    return initialize(row,records)

def http_url(value):
    url = urlparse(value)
    if url.scheme not in ['http','https'] or not url.hostname or url.username or url.password: raise ValueError('HTTP(S) URL without credentials required')

def unique(rows,row,fields):
    if any(all(r[f]==row[f] for f in fields) for r in rows): raise ValueError('Duplicate '+', '.join(fields))

def initialize(row,records):
    http_url(row['target'])
    try: payload=json.loads(row['payload'])
    except ValueError: raise ValueError('Payload must be valid JSON')
    if not isinstance(payload,dict): raise ValueError('Payload must be a JSON object')
    return dict(row,status='queued',attempts=0,last_error=None,response_status=None)
def summary(rows): return {'deliveries':len(rows),'delivered':sum(r['status']=='delivered' for r in rows),'failed':sum(r['status']=='failed' for r in rows),'attempts':sum(r['attempts'] for r in rows)}
def transition(row,action):
    if action!='deliver' or row['status']=='delivered': raise ValueError('Only queued or failed deliveries can be delivered')
    row=dict(row,attempts=row['attempts']+1)
    try:
        request=Request(row['target'],data=row['payload'].encode(),headers={'Content-Type':'application/json','X-Delivery-ID':str(row['id'])},method='POST')
        with urlopen(request,timeout=3) as response: row.update(status='delivered',response_status=response.status,last_error=None)
    except Exception as exc: row.update(status='failed',last_error=str(exc),response_status=None)
    return row
