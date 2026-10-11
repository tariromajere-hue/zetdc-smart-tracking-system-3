"""Create explicit development fixtures. Existing rows are never overwritten."""
import argparse,json,os,time
from pathlib import Path
from sqlalchemy import select,insert
from core import Service,meters,users,STAGES

def seed(service,password):
    names=[('procurement','Procurement','worker'),('stores','Stores','worker'),('tester','Meter Test','worker'),('depot','Depot','worker'),('installer','Contractor','worker'),('hes_officer','HES','hes'),('manager','Management','manager')]
    for name,dep,role in names:
        with service.engine.connect() as c:exists=c.execute(select(users.c.username).where(users.c.username==name)).first()
        if not exists:service.add_user(name,password,dep,role)
    with service.engine.begin() as c:
        for i in range(1,101):
            mid=f'DEMO-{i:04d}'
            if c.execute(select(meters.c.id).where(meters.c.id==mid)).first():continue
            dep='Contractor' if i<=80 else STAGES[(i-81)%4]
            fixture='success' if i<=60 or i>80 else ['rejected','timeout','pending','wrong_receipt'][(i-61)%4]
            c.execute(insert(meters).values(id=mid,department=dep,entered_at=service.clock()-(i%6)*86400,revision=0,account=f'ACC-{i:04d}',ct='100/5',hes='HES_ISKRA' if i%2 else 'HES_SECURE',state='not_installed',reason='',receipt='',attempt_id='',started_at=0,elapsed_ms=0,fixture=fixture))
    return names
if __name__=='__main__':
    import getpass
    pw=os.getenv('DEMO_PASSWORD') or getpass.getpass('Set development worker password (minimum 12 characters): ')
    seed(Service(),pw);print('Development fixtures ready. Users: procurement, stores, tester, depot, installer, hes_officer, manager.')
