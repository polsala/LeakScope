"""Genuine Python 2.7 generated ORM/wizard/job workload, with independent truth.

No production database or business operation. Commands on stdin drive this
isolated fixture; LeakScope never executes these commands inside a real ERP.
"""
from __future__ import print_function
import json
import os
import sys
import time
import gc
from contextlib import contextmanager

held=[]
cache={}
completed=0
agent=None
if os.getenv('LEAKSCOPE_FIXTURE_AGENT')=='1':
    import leakscope_agent as agent
    agent.initialize()


@contextmanager
def operation():
    if agent:
        with agent.safe_operation('erp.generate_invoices',module='fixture',model='fixture.invoice',method='create'):
            yield
    else:
        yield


def execute(mode,count):
    global completed
    start=time.time()
    cpu=time.clock()
    with operation():
        # Generated query rows, ORM dictionaries, line items, and wizard results.
        rows=[{'id':i,'partner':'generated-%d'%i,'payload':('%d-'%i)+'x'*4096,
               'lines':[(j,j*.21) for j in range(4)]} for i in range(count)]
        result={'count':len(rows),'total':sum(sum(v[1] for v in r['lines']) for r in rows)}
        if mode=='leak':
            held.append(rows)
        elif mode=='cache':
            for row in rows:
                cache[row['id']%256]=row
        elif mode=='spike':
            held.append(rows)
        elif mode=='cooldown':
            del held[:]
            cache.clear()
            gc.collect()
        completed+=1
        assert result['count']==count
    return {'elapsed_seconds':time.time()-start,'cpu_seconds':time.clock()-cpu}


def truth():
    return {'pid':os.getpid(),'version':list(sys.version_info[:3]),'completed':completed,
            'retained_records':sum(len(batch) for batch in held),'cache_records':len(cache),
            'retained_payload_bytes':sum(len(row['payload']) for batch in held for row in batch)}


print(json.dumps(truth()))
sys.stdout.flush()
for line in iter(sys.stdin.readline,''):
    parts=line.strip().split()
    if not parts:
        continue
    if parts[0]=='quit':
        break
    count=int(parts[1]) if len(parts)>1 else 256
    if not 1<=count<=4096:
        raise ValueError('Fixture count outside controlled bounds')
    measured=execute(parts[0],count)
    print(json.dumps(dict(truth(),**measured)))
    sys.stdout.flush()
