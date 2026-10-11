"""Custody and commissioning process model. No predictive training or real HES claims."""
import os,json,time,secrets,hashlib,hmac,math,uuid
from pathlib import Path
from datetime import datetime,timezone
import httpx
from sqlalchemy import create_engine,MetaData,Table,Column,String,Float,Integer,Text,select,update,insert

STAGES=['Procurement','Stores','Meter Test','Depot','Contractor']
SLA_SECONDS=3*24*3600
BASE=Path(__file__).parent
meta=MetaData()
users=Table('workers',meta,Column('username',String,primary_key=True),Column('password_hash',Text),Column('department',String),Column('role',String),Column('failed',Integer,default=0),Column('locked_until',Float,default=0))
meters=Table('meters',meta,Column('id',String,primary_key=True),Column('department',String),Column('entered_at',Float),Column('revision',Integer),Column('account',String),Column('ct',String),Column('hes',String),Column('state',String),Column('reason',Text),Column('receipt',Text),Column('attempt_id',String),Column('started_at',Float),Column('elapsed_ms',Float),Column('fixture',String))
sessions=Table('sessions',meta,Column('token_hash',String,primary_key=True),Column('username',String),Column('expires',Float))
audit=Table('audit',meta,Column('id',String,primary_key=True),Column('meter_id',String),Column('at',Float),Column('actor',String),Column('action',String),Column('detail',Text))
notices=Table('notifications',meta,Column('id',String,primary_key=True),Column('event_key',String,unique=True),Column('meter_id',String),Column('recipient',String),Column('channel',String),Column('status',String),Column('created_at',Float),Column('message',Text),Column('provider_id',String),Column('attempts',Integer),Column('last_error',Text))

def hash_password(password,salt=None):
    salt=salt or secrets.token_hex(16)
    return salt+':'+hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),210000).hex()
def password_ok(password,stored):
    return isinstance(password,str) and hmac.compare_digest(hash_password(password,stored.split(':')[0]),stored)
def need(ok,message):
    if not ok:raise ValueError(message)
def clean_id(value):return str(value).strip().upper()

class HESGateway:
    def __init__(self,mode='simulator'):self.mode=mode
    def request(self,meter,attempt,manual=False,reference=''):
        if self.mode=='simulator':
            fixture=meter['fixture']
            if manual:
                if reference!='SIM-MANUAL-'+meter['id']:return {'status':'unconfirmed','reason':'Simulator receipt reference not verified'}
                return {'status':'connected','meter_id':meter['id'],'hes':meter['hes'],'receipt_id':reference,'confirmed_at':datetime.now(timezone.utc).isoformat(),'simulated':True}
            if fixture=='timeout':raise TimeoutError('HES simulator timeout')
            if fixture=='rejected':return {'status':'rejected','reason':'HES simulator rejected provisioning'}
            if fixture=='pending':return {'status':'accepted','reason':'Accepted is not a connection acknowledgement'}
            if fixture=='wrong_receipt':return {'status':'connected','meter_id':'WRONG-METER','hes':meter['hes'],'receipt_id':'WRONG','confirmed_at':datetime.now(timezone.utc).isoformat()}
            return {'status':'connected','meter_id':meter['id'],'hes':meter['hes'],'receipt_id':'SIM-'+attempt,'confirmed_at':datetime.now(timezone.utc).isoformat(),'simulated':True}
        url=os.getenv(meter['hes']+'_URL','');token=os.getenv(meter['hes']+'_TOKEN','')
        need(url.startswith('https://') and token,'Authorised HTTPS HES gateway is not configured')
        route='/confirm-manual' if manual else '/commission'
        r=httpx.post(url.rstrip('/')+route,json={'meter_id':meter['id'],'account':meter['account'],'ct_ratio':meter['ct'],'request_id':attempt,'reference':reference},headers={'Authorization':'Bearer '+token,'Idempotency-Key':attempt},timeout=12,follow_redirects=False)
        r.raise_for_status();return r.json()

def confirmed(response,meter):
    if not isinstance(response,dict):return False
    if response.get('status')!='connected' or response.get('meter_id')!=meter['id'] or response.get('hes')!=meter['hes'] or not response.get('receipt_id'):return False
    try:
        date=datetime.fromisoformat(response['confirmed_at'].replace('Z','+00:00'))
        return date.tzinfo is not None and date.timestamp()<=time.time()+300
    except (KeyError,ValueError,TypeError):return False

class Service:
    def __init__(self,url=None,gateway=None,clock=time.time):
        url=url or os.getenv('DATABASE_URL','sqlite:///meter_demo.db')
        if url.startswith('postgres://'):url=url.replace('postgres://','postgresql+psycopg://',1)
        if url.startswith('postgresql://'):url=url.replace('postgresql://','postgresql+psycopg://',1)
        if os.getenv('VERCEL') and not url.startswith('postgresql+psycopg://'):raise RuntimeError('Vercel requires persistent PostgreSQL DATABASE_URL')
        self.engine=create_engine(url,connect_args={'check_same_thread':False,'timeout':30} if url.startswith('sqlite') else {},pool_pre_ping=True)
        meta.create_all(self.engine);self.clock=clock;self.gateway=gateway or HESGateway(os.getenv('HES_MODE','simulator'))
    def add_user(self,username,password,department,role='worker'):
        need(len(password)>=12,'Use a password of at least 12 characters')
        need(department in STAGES+['HES','Management'],'Unknown department')
        need(role in ['worker','hes','manager'],'Unknown role')
        with self.engine.begin() as c:c.execute(insert(users).values(username=username,password_hash=hash_password(password),department=department,role=role,failed=0,locked_until=0))
    def verify(self,username,password):
        with self.engine.begin() as c:
            u=c.execute(select(users).where(users.c.username==username)).mappings().first()
            if not u:
                hash_password(str(password),'00'*16);raise ValueError('Invalid credentials')
            if u['locked_until']>self.clock():raise ValueError('Account temporarily locked')
            ok=password_ok(password,u['password_hash'])
            if not ok:
                count=u['failed']+1;c.execute(update(users).where(users.c.username==username).values(failed=count,locked_until=self.clock()+900 if count>=5 else 0))
            else:c.execute(update(users).where(users.c.username==username).values(failed=0,locked_until=0))
        need(ok,'Invalid credentials');return dict(u)
    def login(self,username,password):
        u=self.verify(username,password);token=secrets.token_urlsafe(32)
        with self.engine.begin() as c:c.execute(insert(sessions).values(token_hash=hashlib.sha256(token.encode()).hexdigest(),username=username,expires=self.clock()+3600))
        return token,{k:u[k] for k in ['username','department','role']}
    def actor(self,token):
        with self.engine.connect() as c:
            u=c.execute(select(users).join(sessions,users.c.username==sessions.c.username).where(sessions.c.token_hash==hashlib.sha256(token.encode()).hexdigest(),sessions.c.expires>self.clock())).mappings().first()
        need(u,'Sign in again');return dict(u)
    def logout(self,token):
        with self.engine.begin() as c:c.execute(sessions.delete().where(sessions.c.token_hash==hashlib.sha256(token.encode()).hexdigest()))
    def log(self,c,meter,actor,action,detail):
        c.execute(insert(audit).values(id=uuid.uuid4().hex,meter_id=meter,at=self.clock(),actor=actor,action=action,detail=json.dumps(detail)))
    def notify(self,c,event,meter,recipient,message):
        for channel in ['app','email','whatsapp']:
            key=event+':'+channel
            if c.execute(select(notices.c.id).where(notices.c.event_key==key)).first():continue
            c.execute(insert(notices).values(id=uuid.uuid4().hex,event_key=key,meter_id=meter,recipient=recipient,channel=channel,status='available' if channel=='app' else 'queued',created_at=self.clock(),message=message,provider_id='',attempts=0,last_error=''))
    def register(self,token,meter_id,account,ct,hes):
        u=self.actor(token);need(u['department']=='Procurement' or u['role']=='manager','Procurement permission required')
        meter_id=clean_id(meter_id);need(3<=len(meter_id)<=80 and meter_id.replace('-','').isalnum(),'Invalid meter identifier')
        need(account.strip() and ct.strip() and hes in ['HES_ISKRA','HES_SECURE'],'Account, CT and supported HES required')
        with self.engine.begin() as c:
            need(not c.execute(select(meters.c.id).where(meters.c.id==meter_id)).first(),'Meter already exists')
            c.execute(insert(meters).values(id=meter_id,department='Procurement',entered_at=self.clock(),revision=0,account=account.strip(),ct=ct.strip(),hes=hes,state='not_installed',reason='',receipt='',attempt_id='',started_at=0,elapsed_ms=0,fixture='success'))
            self.log(c,meter_id,u['username'],'registered',{'department':'Procurement'})
        return self.meter(token,meter_id)
    def meter(self,token,meter_id):
        self.actor(token)
        with self.engine.connect() as c:m=c.execute(select(meters).where(meters.c.id==clean_id(meter_id))).mappings().first()
        need(m,'Unknown meter');return dict(m)
    def handover(self,token,meter_id,revision,sender_password,receiver,receiver_password):
        sender=self.actor(token);self.verify(sender['username'],sender_password);recipient=self.verify(receiver,receiver_password)
        need(sender['username']!=receiver,'Two distinct workers must sign')
        with self.engine.begin() as c:
            m=c.execute(select(meters).where(meters.c.id==clean_id(meter_id))).mappings().first();need(m,'Unknown meter')
            need(m['department']==sender['department'] and sender['role']=='worker','Only the current releasing worker can sign')
            i=STAGES.index(m['department']);need(i<4,'Already issued to contractor')
            need(recipient['department']==STAGES[i+1] and recipient['role']=='worker','Receiving worker must belong to the next department')
            result=c.execute(update(meters).where(meters.c.id==m['id'],meters.c.revision==revision,meters.c.department==sender['department']).values(department=recipient['department'],entered_at=self.clock(),revision=revision+1))
            need(result.rowcount==1,'Custody changed; refresh before signing')
            self.log(c,m['id'],sender['username'],'handover',{'from':m['department'],'to':recipient['department'],'released_by':sender['username'],'received_by':receiver})
        return self.meter(token,meter_id)
    def commission(self,token,meter_id,account,ct,installed):
        u=self.actor(token);need(u['department']=='Contractor' and u['role']=='worker','Contractor permission required')
        m=self.meter(token,meter_id)
        need(m['department']=='Contractor','Meter has not been issued to contractor')
        need(installed is True,'Confirm the physical installation')
        need(account.strip()==m['account'] and ct.strip()==m['ct'],'Account or CT ratio mismatch')
        if m['state']=='connected':return m
        need(m['state'] not in ['manual_required','processing'],'Manual HES action or existing request is pending; no automatic retry')
        attempt=uuid.uuid4().hex;start=time.perf_counter()
        with self.engine.begin() as c:
            result=c.execute(update(meters).where(meters.c.id==m['id'],meters.c.revision==m['revision'],meters.c.state==m['state']).values(state='processing',attempt_id=attempt,started_at=self.clock(),revision=m['revision']+1))
            need(result.rowcount==1,'Another request is already processing')
            self.log(c,m['id'],u['username'],'commission_requested',{'request_id':attempt,'hes':m['hes'],'mode':self.gateway.mode})
        try:response=self.gateway.request(m,attempt)
        except Exception as e:response={'status':'failed','reason':type(e).__name__+': connection result not confirmed'}
        ok=confirmed(response,m);elapsed=(time.perf_counter()-start)*1000
        with self.engine.begin() as c:
            result=c.execute(update(meters).where(meters.c.id==m['id'],meters.c.attempt_id==attempt,meters.c.state=='processing').values(state='connected' if ok else 'manual_required',receipt=json.dumps(response) if ok else '',reason='' if ok else str(response.get('reason','HES acknowledgement missing or invalid')),elapsed_ms=elapsed))
            if result.rowcount:
                self.log(c,m['id'],u['username'],'connected' if ok else 'manual_required',{'request_id':attempt,'response':response,'elapsed_ms':elapsed})
                if not ok:self.notify(c,'failed:'+attempt,m['id'],'HES',f"{m['id']}: automatic connection unconfirmed. Manual HES commissioning required.")
        return self.meter(token,meter_id)
    def manual(self,token,meter_id,password,reference):
        u=self.actor(token);need(u['role']=='hes','HES team permission required');self.verify(u['username'],password)
        m=self.meter(token,meter_id);need(m['state']=='manual_required','Meter is not awaiting manual commissioning')
        need(reference.strip(),'HES confirmation reference required')
        try:response=self.gateway.request(m,m['attempt_id'],manual=True,reference=reference.strip())
        except Exception:response={}
        need(confirmed(response,m),'Manual HES completion was not confirmed')
        with self.engine.begin() as c:
            result=c.execute(update(meters).where(meters.c.id==m['id'],meters.c.state=='manual_required',meters.c.revision==m['revision']).values(state='connected',receipt=json.dumps(response),reason='',revision=m['revision']+1))
            need(result.rowcount==1,'Record changed; refresh')
            self.log(c,m['id'],u['username'],'manual_connected',{'reference':reference,'response':response})
        return self.meter(token,meter_id)
    def sweep(self):
        count=0
        with self.engine.begin() as c:
            for m in c.execute(select(meters)).mappings().all():
                if self.clock()-m['entered_at']>SLA_SECONDS and m['state']!='connected':
                    self.notify(c,f"overdue:{m['id']}:{m['entered_at']}",m['id'],'Management',f"{m['id']} held by {m['department']} beyond three days.");count+=1
                if m['state']=='processing' and self.clock()-m['started_at']>120:
                    c.execute(update(meters).where(meters.c.id==m['id'],meters.c.state=='processing').values(state='manual_required',reason='Request interrupted; reconcile with HES manually'))
                    self.notify(c,'failed:'+m['attempt_id'],m['id'],'HES',f"{m['id']}: interrupted request requires manual HES reconciliation.")
                    self.log(c,m['id'],'scheduler','interrupted_request',{})
        return count
    def snapshot(self,token):
        self.actor(token)
        with self.engine.connect() as c:
            data={name:[dict(r) for r in c.execute(select(t)).mappings().all()] for name,t in [('meters',meters),('notifications',notices),('audit',audit)]}
        for m in data['meters']:m['held_days']=round((self.clock()-m['entered_at'])/86400,3);m['overdue']=self.clock()-m['entered_at']>SLA_SECONDS and m['state']!='connected'
        data['mode']=self.gateway.mode;data['sla_days']=3;return data
    def dispatch(self,sender):
        with self.engine.connect() as c:pending=[dict(r) for r in c.execute(select(notices).where(notices.c.status.in_(['queued','failed']))).mappings().all()]
        for n in pending:
            with self.engine.begin() as c:
                claimed=c.execute(update(notices).where(notices.c.id==n['id'],notices.c.status==n['status']).values(status='sending',attempts=n['attempts']+1))
            if not claimed.rowcount:continue
            try:status,pid=sender(n);need(status in ['simulated','accepted','delivered'],'Unknown delivery status');err=''
            except Exception as e:status,pid,err='failed','',type(e).__name__
            with self.engine.begin() as c:c.execute(update(notices).where(notices.c.id==n['id']).values(status=status,provider_id=pid,last_error=err))
        return len(pending)

def send_notification(n):
    if os.getenv('NOTIFICATION_MODE','simulator')=='simulator':return 'simulated','SIM-'+n['id']
    recipient=os.getenv(('HES' if n['recipient']=='HES' else 'MANAGER')+('_EMAIL' if n['channel']=='email' else '_WHATSAPP'),'')
    need(recipient,'Notification recipient is not configured')
    if n['channel']=='email':
        import smtplib,ssl
        from email.message import EmailMessage
        msg=EmailMessage();msg['From']=os.environ['SMTP_FROM'];msg['To']=recipient;msg['Subject']='Smart meter action required';msg['Message-ID']='<'+n['id']+'@meter-project.local>';msg.set_content(n['message'])
        with smtplib.SMTP_SSL(os.environ['SMTP_HOST'],int(os.getenv('SMTP_PORT','465')),context=ssl.create_default_context(),timeout=12) as smtp:
            smtp.login(os.environ['SMTP_USER'],os.environ['SMTP_PASSWORD']);rejected=smtp.send_message(msg)
            need(not rejected,'Email rejected')
        return 'accepted',msg['Message-ID']
    sid=os.environ['TWILIO_ACCOUNT_SID'];content=os.environ['TWILIO_CONTENT_SID']
    r=httpx.post(f'https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json',auth=(sid,os.environ['TWILIO_AUTH_TOKEN']),data={'From':os.environ['TWILIO_WHATSAPP_FROM'],'To':recipient,'ContentSid':content,'ContentVariables':json.dumps({'1':n['message']})},timeout=12)
    r.raise_for_status();return 'accepted',r.json()['sid']
