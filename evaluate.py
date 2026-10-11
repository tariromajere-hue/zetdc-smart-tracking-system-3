"""Requirement-based evaluation. Expected outcomes are fixed before executing the app."""
import sys,os,json,time,tempfile,statistics
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select,update,insert
from core import Service,meters,users,notices,audit,HESGateway,SLA_SECONDS
from seed import seed
OUT=Path(__file__).resolve().parents[1]/'evidence';OUT.mkdir(exist_ok=True)
PASSWORD='Prototype-Test-2026!'
checks=[];cases=[]
def check(group,name,fn):
    start=time.perf_counter()
    try:fn();checks.append({'group':group,'name':name,'passed':True,'elapsed_ms':(time.perf_counter()-start)*1000})
    except Exception as e:checks.append({'group':group,'name':name,'passed':False,'error':str(e)})
def eq(a,b):assert a==b,(a,b)
def rejected(fn):
    try:fn()
    except ValueError:return
    raise AssertionError('Request incorrectly accepted')
temp=tempfile.TemporaryDirectory(ignore_cleanup_errors=True);s=Service('sqlite:///'+str(Path(temp.name)/'evaluation.db'));seed(s,PASSWORD)
tokens={u:s.login(u,PASSWORD)[0] for u in ['procurement','stores','tester','depot','installer','hes_officer','manager']}
check('Tracking','Password hashes are salted, not plaintext',lambda: eq(s.verify('stores',PASSWORD)['password_hash']==PASSWORD,False))
check('Tracking','Incorrect login password rejected',lambda:rejected(lambda:s.login('stores','incorrect')))
check('Tracking','Unknown account rejected',lambda:rejected(lambda:s.login('unknown',PASSWORD)))
check('Tracking','Unauthenticated register rejected',lambda:rejected(lambda:s.register('invalid','NEW-1','A','100/5','HES_ISKRA')))
check('Tracking','Contractor cannot register procurement',lambda:rejected(lambda:s.register(tokens['installer'],'NEW-1','A','100/5','HES_ISKRA')))
check('Tracking','Procurement can register meter',lambda:eq(s.register(tokens['procurement'],'NEW-1','A','100/5','HES_ISKRA')['department'],'Procurement'))
check('Tracking','Duplicate meter rejected',lambda:rejected(lambda:s.register(tokens['procurement'],'NEW-1','A','100/5','HES_ISKRA')))
check('Tracking','Unknown HES rejected',lambda:rejected(lambda:s.register(tokens['procurement'],'NEW-2','A','100/5','OTHER')))
check('Tracking','Bad releasing password blocks transfer',lambda:rejected(lambda:s.handover(tokens['procurement'],'NEW-1',0,'wrong','stores',PASSWORD)))
check('Tracking','Bad receiving password blocks transfer',lambda:rejected(lambda:s.handover(tokens['procurement'],'NEW-1',0,PASSWORD,'stores','wrong')))
check('Tracking','Cannot skip to depot',lambda:rejected(lambda:s.handover(tokens['procurement'],'NEW-1',0,PASSWORD,'depot',PASSWORD)))
check('Tracking','One person cannot sign twice',lambda:rejected(lambda:s.handover(tokens['procurement'],'NEW-1',0,PASSWORD,'procurement',PASSWORD)))
check('Tracking','Rejected signatures preserve custody',lambda:eq(s.meter(tokens['manager'],'NEW-1')['department'],'Procurement'))
for i,(a,b) in enumerate(zip(['procurement','stores','tester','depot'],['stores','tester','depot','installer'])):
    check('Tracking','Password handover '+a+' to '+b,lambda a=a,b=b,i=i:eq(s.handover(tokens[a],'NEW-1',i,PASSWORD,b,PASSWORD)['revision'],i+1))
check('Tracking','Repeated old handover rejected',lambda:rejected(lambda:s.handover(tokens['procurement'],'NEW-1',0,PASSWORD,'stores',PASSWORD)))
check('Tracking','Custody audit contains both workers',lambda:eq(len([a for a in s.snapshot(tokens['manager'])['audit'] if a['meter_id']=='NEW-1' and a['action']=='handover' and 'received_by' in a['detail']]),4))
# Use a separate clock-controlled store to test the exact policy boundary.
bound=Service('sqlite:///'+str(Path(temp.name)/'boundary.db'),clock=lambda:1000000.0);seed(bound,PASSWORD);bt=bound.login('manager',PASSWORD)[0]
with bound.engine.begin() as c:c.execute(update(meters).values(entered_at=1000000.0))
with bound.engine.begin() as c:c.execute(update(meters).where(meters.c.id=='DEMO-0001').values(entered_at=1000000.0-SLA_SECONDS))
check('Tracking','Exactly 72 hours does not trigger overdue',lambda:eq(bound.sweep(),0))
bound.clock=lambda:1000001.0
check('Tracking','72 hours plus one second triggers overdue',lambda:eq(bound.sweep(),1))
check('Tracking','All three manager channels created',lambda:eq(sorted(n['channel'] for n in bound.snapshot(bt)['notifications']),['app','email','whatsapp']))
check('Tracking','Repeat scheduler does not duplicate event',lambda:(bound.sweep(),eq(len(bound.snapshot(bt)['notifications']),3)))
check('Tracking','Elapsed duration is preserved',lambda:eq(bound.snapshot(bt)['meters'][0]['held_days'],3.0))
check('Tracking','Email and WhatsApp simulated separately',lambda:(bound.dispatch(lambda n:('simulated','SIM-'+n['channel'])),eq(sorted(n['status'] for n in bound.snapshot(bt)['notifications']),['available','simulated','simulated'])))
# Installation input validation, permissions and idempotence.
check('Commissioning','Non-contractor cannot commission',lambda:rejected(lambda:s.commission(tokens['manager'],'DEMO-0001','ACC-0001','100/5',True)))
check('Commissioning','Unissued meter cannot commission',lambda:rejected(lambda:s.commission(tokens['installer'],'DEMO-0081','ACC-0081','100/5',True)))
check('Commissioning','Wrong account rejected',lambda:rejected(lambda:s.commission(tokens['installer'],'DEMO-0001','WRONG','100/5',True)))
check('Commissioning','Wrong CT rejected',lambda:rejected(lambda:s.commission(tokens['installer'],'DEMO-0001','ACC-0001','5/5',True)))
check('Commissioning','Installation confirmation required',lambda:rejected(lambda:s.commission(tokens['installer'],'DEMO-0001','ACC-0001','100/5',False)))
check('Commissioning','Unknown meter rejected',lambda:rejected(lambda:s.commission(tokens['installer'],'UNKNOWN','A','100/5',True)))
for i in range(1,81):
    mid=f'DEMO-{i:04d}';expected='connected' if i<=60 else 'manual_required';start=time.perf_counter()
    result=s.commission(tokens['installer'],mid,f'ACC-{i:04d}','100/5',True)
    cases.append({'meter_id':mid,'expected':expected,'actual':result['state'],'passed':result['state']==expected,'fixture':result['fixture'],'hes':result['hes'],'request_elapsed_ms':result['elapsed_ms'],'whole_call_ms':(time.perf_counter()-start)*1000})
check('Commissioning','80 fixed scenarios reach expected state',lambda:eq(sum(c['passed'] for c in cases),80))
check('Commissioning','Connected request is idempotent',lambda:(s.commission(tokens['installer'],'DEMO-0001','ACC-0001','100/5',True),eq(len([a for a in s.snapshot(tokens['manager'])['audit'] if a['meter_id']=='DEMO-0001' and a['action']=='commission_requested']),1)))
check('Commissioning','Failure cannot automatically retry',lambda:rejected(lambda:s.commission(tokens['installer'],'DEMO-0061','ACC-0061','100/5',True)))
check('Commissioning','All failed meters have three HES notifications',lambda:eq(len([n for n in s.snapshot(tokens['manager'])['notifications'] if n['recipient']=='HES']),60))
check('Commissioning','Contractor cannot confirm manual completion',lambda:rejected(lambda:s.manual(tokens['installer'],'DEMO-0061',PASSWORD,'SIM-MANUAL-DEMO-0061')))
check('Commissioning','HES password is rechecked',lambda:rejected(lambda:s.manual(tokens['hes_officer'],'DEMO-0061','wrong','SIM-MANUAL-DEMO-0061')))
check('Commissioning','Unverified manual receipt is rejected',lambda:rejected(lambda:s.manual(tokens['hes_officer'],'DEMO-0061',PASSWORD,'invented')))
manual=[]
for i in range(61,81):
    mid=f'DEMO-{i:04d}';result=s.manual(tokens['hes_officer'],mid,PASSWORD,'SIM-MANUAL-'+mid);manual.append({'meter_id':mid,'passed':result['state']=='connected'})
check('Commissioning','20 manual simulator confirmations verified',lambda:eq(sum(m['passed'] for m in manual),20))
check('Commissioning','Already completed manual confirmation rejected',lambda:rejected(lambda:s.manual(tokens['hes_officer'],'DEMO-0061',PASSWORD,'SIM-MANUAL-DEMO-0061')))
# Interrupted requests and provider failures must not become successes.
with s.engine.begin() as c:c.execute(update(meters).where(meters.c.id=='DEMO-0080').values(state='processing',started_at=s.clock()-121))
check('Commissioning','Interrupted request requires manual reconciliation',lambda:(s.sweep(),eq(s.meter(tokens['manager'],'DEMO-0080')['state'],'manual_required')))
def fail_sender(n):raise TimeoutError('provider unavailable')
check('Notifications','Provider failure remains failed, not delivered',lambda:(s.dispatch(fail_sender),eq(all(n['status']=='failed' for n in s.snapshot(tokens['manager'])['notifications'] if n['channel']!='app'),True)))
check('Notifications','Failed notification can be retried independently',lambda:(s.dispatch(lambda n:('accepted','provider-test-id')),eq(all(n['status']=='accepted' for n in s.snapshot(tokens['manager'])['notifications'] if n['channel']!='app'),True)))
check('Notifications','Provider acceptance is not delivered status',lambda:eq(any(n['status']=='delivered' for n in s.snapshot(tokens['manager'])['notifications']),False))
check('Tracking','Data survives service restart',lambda:eq(Service('sqlite:///'+str(Path(temp.name)/'evaluation.db')).meter(tokens['manager'],'NEW-1')['department'],'Contractor'))
# Concurrent duplicate handovers must produce only one custody change.
s.register(tokens['procurement'],'RACE-1','A','100/5','HES_ISKRA')
def race_check():
    from concurrent.futures import ThreadPoolExecutor
    def attempt():
        try:s.handover(tokens['procurement'],'RACE-1',0,PASSWORD,'stores',PASSWORD);return True
        except ValueError:return False
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:attempt(),range(2)))
    eq(sum(results),1)
check('Tracking','Concurrent duplicate handovers transfer once',race_check)
check('Tracking','Logout revokes session',lambda:(s.logout(tokens['stores']),rejected(lambda:s.actor(tokens['stores']))))
# HTTP routes exercise validation and authorization separately from direct core calls.
os.environ['DATABASE_URL']='sqlite:///'+str(Path(temp.name)/'http.db')
from fastapi.testclient import TestClient
from app import app,service
hs=service();seed(hs,PASSWORD);client=TestClient(app)
check('API','Anonymous dashboard denied',lambda:eq(client.get('/api/dashboard').status_code,401))
check('API','Login endpoint issues token',lambda:eq(client.post('/api/login',json={'username':'manager','password':PASSWORD}).status_code,200))
ht=client.post('/api/login',json={'username':'installer','password':PASSWORD}).json()['token'];headers={'Authorization':'Bearer '+ht}
check('API','Malformed commissioning body rejected',lambda:eq(client.post('/api/commission',headers=headers,json={}).status_code,422))
check('API','Contractor cannot run manager alert job',lambda:eq(client.post('/api/check-alerts',headers=headers).status_code,403))
check('API','Unauthenticated cron denied',lambda:eq(client.get('/api/cron').status_code,401))
check('API','HTTP commission returns confirmed simulator state',lambda:eq(client.post('/api/commission',headers=headers,json={'meter_id':'DEMO-0001','account':'ACC-0001','ct':'100/5','installed':True}).json()['state'],'connected'))
check('API','Unknown barcode fails without connection',lambda:eq(client.get('/api/meter/UNKNOWN',headers=headers).status_code,400))
summary={'evaluation':'fixed development scenarios, not field observations','acceptance_target_percent':90,'functional_checks':len(checks),'functional_passed':sum(c['passed'] for c in checks),'groups':{g:{'passed':sum(c['passed'] for c in checks if c['group']==g),'total':sum(c['group']==g for c in checks)} for g in sorted(set(c['group'] for c in checks))},'commissioning_scenarios':len(cases),'correct_scenario_outcomes':sum(c['passed'] for c in cases),'automatic_connections':60,'automatic_connection_rate_percent':75,'manual_required':20,'manual_confirmations':sum(x['passed'] for x in manual),'connection_time_ms':{'median':statistics.median(c['request_elapsed_ms'] for c in cases if c['actual']=='connected'),'max':max(c['request_elapsed_ms'] for c in cases if c['actual']=='connected')},'live_hes_tests':0,'live_email_deliveries':0,'live_whatsapp_deliveries':0,'physical_phone_tests':0}
for name,data in [('functional_checks',checks),('commissioning_cases',cases),('manual_cases',manual),('summary',summary),('audit_sample',s.snapshot(tokens['manager']))]:(OUT/(name+'.json')).write_text(json.dumps(data,indent=2))
print(json.dumps(summary,indent=2));print('FAILURES',[c for c in checks if not c['passed']]);assert all(c['passed'] for c in checks) and all(c['passed'] for c in cases)

client.close();s.engine.dispose();bound.engine.dispose();hs.engine.dispose()
