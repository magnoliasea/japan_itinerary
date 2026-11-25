"""Apply explicitly user-reviewed Expedia quotes; never pretend to query Expedia."""
import json,re,datetime,math
from edit_atlas import load_html,P
GROUPS={'01-04':'Asakusa','04-07':'Kyoto','07-08':'Osaka','08-09':'Hakone','09-10':'Asakusa','10-11':'Asakusa','04-05':'Osaka','05-08':'Kyoto'}
def hotelid(h):
 m=re.search(r'\.h(\d+)\.',h.get('url',''));return m[1] if m else ''
def apply_refresh(req):
 h,m,d=load_html();k=req.get('stay');rows=req.get('quotes');stamp=req.get('checkedAt')
 if k not in GROUPS or not isinstance(rows,list) or not 1<=len(rows)<=40:raise ValueError('Invalid stay or quotes')
 if not isinstance(stamp,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z',stamp):raise ValueError('Invalid timestamp')
 datetime.datetime.fromisoformat(stamp.replace('Z','+00:00'))
 existing={hotelid(x):x for x in d['hotels'][k]};seen=set();a,b=k.split('-');adults=2 if k=='10-11' else 4
 for q in rows:
  if not isinstance(q,dict):raise ValueError('Invalid quote')
  hid=str(q.get('id',''));price=q.get('price');status=q.get('status')
  if not re.fullmatch(r'\d{1,15}',hid) or hid in seen or status not in ['quoted','not_found','unknown']:raise ValueError('Invalid ID/status or duplicate')
  seen.add(hid)
  if status=='quoted' and (isinstance(price,bool) or not isinstance(price,(int,float)) or not math.isfinite(price) or not 0<price<=100000):raise ValueError('Invalid USD total')
  if status!='quoted':price=None
  item=existing.get(hid)
  if item is None:
   if status!='quoted' or q.get('privateBathroom') is not True or not isinstance(q.get('name'),str) or not q['name'].strip() or len(q['name'])>200:raise ValueError('New candidates require name, quote and confirmed private bathroom')
   if GROUPS[k]=='Asakusa' and (q.get('area')!='Asakusa' or not all(isinstance(q.get(f),(int,float)) and not isinstance(q.get(f),bool) and 0<=q[f]<=15 for f in ['walk','stationWalk'])):raise ValueError('New Tokyo candidates must be in Asakusa and within 15 min walking of Senso-ji and transit')
   item={'name':q['name'],'rating':'','stars':None,'walk':q.get('walk'),'stationWalk':q.get('stationWalk'),'room':'Private bathroom reported by importer; confirm exact occupancy and room','details':'New user-reviewed candidate; no independent room-level verification.','src':'','nights':int(b)-int(a),'url':f'https://www.expedia.com/.h{hid}.Hotel-Information?chkin=2027-01-{a}&chkout=2027-01-{b}&rm1=a{adults}'}
   d['hotels'][k].append(item)
  item['price']=price;item['quoteStatus']=status;item['quoteCheckedAt']=stamp;item['quoteSource']='User-reviewed Expedia import'
  if isinstance(q.get('note'),str):item['quoteNote']=q['note'][:500]
 d.setdefault('hotelRefresh',{})[k]=stamp
 serialized=json.dumps(d,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
 P.write_text(h[:m.start(2)]+serialized+h[m.end(2):],encoding='utf-8')
 print('Saved reviewed hotel quotes for',k)
