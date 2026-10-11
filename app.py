from pathlib import Path
import os,secrets
from functools import lru_cache
from fastapi import FastAPI,Header,HTTPException,Request
from fastapi.responses import FileResponse,JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,Field
from core import Service,send_notification

app=FastAPI(title='Smart Meter Custody and Commissioning',version='2.0')
BASE=Path(__file__).parent
@lru_cache
def service():return Service()
def auth(authorization):
    if not authorization or not authorization.startswith('Bearer '):raise HTTPException(401,'Sign in required')
    return authorization[7:]
@app.exception_handler(ValueError)
async def invalid(request,exc):return JSONResponse(status_code=400,content={'detail':str(exc)})
@app.middleware('http')
async def security(request:Request,call_next):
    if int(request.headers.get('content-length','0'))>20000:return JSONResponse(status_code=413,content={'detail':'Request too large'})
    r=await call_next(request);r.headers['X-Content-Type-Options']='nosniff';r.headers['Cache-Control']='no-store';r.headers['Referrer-Policy']='same-origin';r.headers['Permissions-Policy']='camera=(self)';return r
class Login(BaseModel):
    username:str=Field(max_length=80)
    password:str=Field(max_length=256)
class Register(BaseModel):
    meter_id:str=Field(max_length=80)
    account:str=Field(max_length=80)
    ct:str=Field(max_length=30)
    hes:str
class Handover(BaseModel):
    meter_id:str
    revision:int=Field(ge=0)
    sender_password:str=Field(max_length=256)
    receiver:str
    receiver_password:str=Field(max_length=256)
class Commission(BaseModel):
    meter_id:str
    account:str
    ct:str
    installed:bool
class Manual(BaseModel):
    meter_id:str
    password:str=Field(max_length=256)
    reference:str=Field(max_length=200)
@app.get('/health')
def health():return {'status':'ok','purpose':'custody and automatic commissioning','mode':os.getenv('HES_MODE','simulator')}
@app.post('/api/login')
def login(body:Login):
    token,user=service().login(body.username,body.password);return {'token':token,'user':user}
@app.post('/api/logout')
def logout(authorization:str|None=Header(default=None)):service().logout(auth(authorization));return {'ok':True}
@app.get('/api/dashboard')
def dashboard(authorization:str|None=Header(default=None)):return service().snapshot(auth(authorization))
@app.get('/api/meter/{meter_id}')
def meter(meter_id:str,authorization:str|None=Header(default=None)):return service().meter(auth(authorization),meter_id)
@app.post('/api/register')
def register(body:Register,authorization:str|None=Header(default=None)):return service().register(auth(authorization),**body.model_dump())
@app.post('/api/handover')
def handover(body:Handover,authorization:str|None=Header(default=None)):return service().handover(auth(authorization),**body.model_dump())
@app.post('/api/commission')
def commission(body:Commission,authorization:str|None=Header(default=None)):return service().commission(auth(authorization),**body.model_dump())
@app.post('/api/manual')
def manual(body:Manual,authorization:str|None=Header(default=None)):return service().manual(auth(authorization),**body.model_dump())
@app.post('/api/check-alerts')
def alerts(authorization:str|None=Header(default=None)):
    u=service().actor(auth(authorization))
    if u['role']!='manager':raise HTTPException(403,'Manager permission required')
    return {'overdue':service().sweep(),'notifications_processed':service().dispatch(send_notification)}
@app.get('/api/cron')
def cron(authorization:str|None=Header(default=None)):
    secret=os.getenv('CRON_SECRET','')
    if not secret or not secrets.compare_digest(authorization or '','Bearer '+secret):raise HTTPException(401,'Scheduler authentication required')
    return {'overdue':service().sweep(),'notifications_processed':service().dispatch(send_notification)}
@app.get('/')
def home():return FileResponse(BASE/'static/index.html')
app.mount('/static',StaticFiles(directory=BASE/'static'),name='static')
