import sys,json
from pathlib import Path

from streamlit.testing.v1 import AppTest
import os
os.environ['DATABASE_URL']='sqlite:///'+str(Path('tests/streamlit_evaluation.db').resolve())
sys.path.insert(0,str(Path('.').resolve()))
from core import Service
from seed import seed
seed(Service(),'Prototype-Test-2026!')
a=AppTest.from_file(str(Path('./streamlit_app.py').resolve()),default_timeout=30).run()
result=[{'name':'Streamlit sign-in renders','passed':not bool(a.exception)}]
if not a.exception:
 a.text_input[0].set_value('installer');a.text_input[1].set_value('Prototype-Test-2026!');a.button[0].click().run();result.append({'name':'Streamlit authenticated commissioning console renders','passed':not bool(a.exception)})
Path('./evidence/streamlit_checks.json').write_text(json.dumps(result,indent=2));print(result)
if a.exception:print(a.exception)
