"""Streamlit commissioning console using the same transactional core as Vercel."""
import os
import streamlit as st
for key in ['DATABASE_URL','HES_MODE','NOTIFICATION_MODE','HES_ISKRA_URL','HES_ISKRA_TOKEN','HES_SECURE_URL','HES_SECURE_TOKEN']:
    try:
        if key in st.secrets:os.environ[key]=str(st.secrets[key])
    except FileNotFoundError:pass
from core import Service
st.set_page_config(page_title='Smart Meter HES Commissioning',layout='wide')
@st.cache_resource
def service():return Service()
s=service()
st.title('Smart Meter HES Commissioning')
st.caption('Scan-triggered process model · no machine-learning delay predictions')
st.info('HES mode: '+s.gateway.mode+'. Simulator confirmations do not connect real utility meters.')
if 'token' not in st.session_state:
    with st.form('login'):
        username=st.text_input('Username');pw=st.text_input('Password',type='password')
        submit=st.form_submit_button('Sign in')
    if submit:
        try:st.session_state.token,st.session_state.user=s.login(username,pw);st.rerun()
        except ValueError as e:st.error(str(e))
    st.stop()
token=st.session_state.token
try:data=s.snapshot(token)
except ValueError:
    del st.session_state.token;st.rerun()
st.write('Signed in as '+st.session_state.user['username'])
if st.button('Sign out'):
    s.logout(token);del st.session_state.token;st.rerun()
cols=st.columns(3)
cols[0].metric('Registered',len(data['meters']));cols[1].metric('Connected',sum(m['state']=='connected' for m in data['meters']));cols[2].metric('Manual HES queue',sum(m['state']=='manual_required' for m in data['meters']))
a,b,c=st.tabs(['Scan and connect','Manual confirmation','Records'])
with a:
    st.write('Use the Vercel scanner for continuous mobile camera decoding, or capture/upload a barcode photograph below.')
    scanner=os.getenv('SCANNER_URL','')
    try:scanner=st.secrets.get('SCANNER_URL',scanner)
    except FileNotFoundError:pass
    if scanner:st.link_button('Open mobile scanner',scanner)
    photo=st.camera_input('Photograph a printed barcode')
    upload=st.file_uploader('Or upload a barcode image',type=['png','jpg','jpeg'])
    if photo or upload:
        try:
            from PIL import Image
            import zxingcpp
            result=zxingcpp.read_barcode(Image.open(photo or upload))
            if result:st.session_state.scanned=result.text;st.success('Read '+result.text)
            else:st.warning('No barcode found. Try again or type the identifier.')
        except Exception as e:st.error('Image could not be decoded: '+type(e).__name__)
    with st.form('connect'):
        mid=st.text_input('Meter ID',value=st.session_state.get('scanned',''))
        acc=st.text_input('Installed account');ct=st.text_input('Installed CT ratio');installed=st.checkbox('I confirm physical installation')
        submit=st.form_submit_button('Validate and request HES connection')
    if submit:
        try:
            result=s.commission(token,mid,acc,ct,installed);st.json({k:result[k] for k in ['id','state','reason','receipt','elapsed_ms']})
        except ValueError as e:st.error(str(e))
with b:
    pending=[m['id'] for m in data['meters'] if m['state']=='manual_required']
    if not pending:st.write('No manual cases in this snapshot.')
    else:
        with st.form('manual'):
            mid=st.selectbox('Unconnected meter',pending);ref=st.text_input('Verified HES reference');pw=st.text_input('HES officer password',type='password');submit=st.form_submit_button('Verify manual completion')
        if submit:
            try:st.json(s.manual(token,mid,pw,ref))
            except ValueError as e:st.error(str(e))
        if s.gateway.mode=='simulator':st.caption('Simulator reference: SIM-MANUAL- followed by meter ID. This does not verify a live HES.')
with c:
    st.dataframe(data['meters']);st.subheader('Notification outcomes');st.dataframe(data['notifications']);st.subheader('Audit');st.dataframe(data['audit'])
st.caption('Run the separate worker or a scheduled cron job for automatic overdue checks and notification dispatch. Streamlit reruns are not a background scheduler.')
