from pathlib import Path
import sys,json


import pymupdf as fitz,zxingcpp
from PIL import Image
out=Path('.');d=fitz.open(out/'Test_Barcodes_100.pdf');crop=Path('tests/barcodes');crop.mkdir(exist_ok=True);results=[]
for i in range(100):
 page=d[i//10];j=i%10;x=35+(j%2)*267;y=90+(j//2)*140
 for kind,clip in [('Code128',(x-10,y+6,x+170,y+47)),('QR',(x+179,y+44,x+245,y+111))]:
  pix=page.get_pixmap(matrix=fitz.Matrix(3,3),clip=fitz.Rect(*clip));im=Image.frombytes('RGB',[pix.width,pix.height],pix.samples);r=zxingcpp.read_barcode(im);results.append({'meter':f'DEMO-{i+1:04d}','format':kind,'passed':bool(r and r.text==f'DEMO-{i+1:04d}')})
  if kind=='Code128':im.save(crop/f'DEMO-{i+1:04d}.png')
for i,p in enumerate(d):p.get_pixmap(matrix=fitz.Matrix(1,1)).save(str(crop/f'page-{i+1}.png'))
(out/'evidence/barcode_checks.json').write_text(json.dumps(results,indent=2));print('Barcode/QR checks',sum(r['passed'] for r in results),'of',len(results))
