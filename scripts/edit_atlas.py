"""Validate one user-approved activity edit; modify only embedded JSON, never executable HTML."""
import os,json,re,pathlib,urllib.request,sys,copy
P=pathlib.Path('index.html')
FIELDS=['time','name','place','travel','hours','price','desc','tip','souvenir','options','url']
def load_html():
 h=P.read_text(encoding='utf-8');m=re.search(r'(<script id="data" type="application/json">)(.*?)(</script>)',h,re.S)
 if not m:raise ValueError('Cannot find embedded itinerary data')
 return h,m,json.loads(m[2])
def route_events(d,r,day):
 if not (0<=r<len(d['variants']) and 0<=day<len(d['variants'][r]['order'])):raise ValueError('Unknown route/day')
 variant=d['variants'][r];base=variant.get('baseRoute',r);k=variant['order'][day]
 if type(base) is not int or not 0<=base<=4:raise ValueError('Unknown base route')
 events=(variant.get('snapshotDays') or (d['ultimate'] if base==4 else d['days']))[k]['events']
 # Match the Osaka-first browser's filtered event order.
 if not variant.get('snapshotDays') and base==1 and k=='osaka':events=[e for e in events if e['name']!='Den Den Town']
 return events

def parse_id(d,ident):
 if not isinstance(ident,str) or not re.fullmatch(r'\d{1,4}-\d{1,2}-\d{1,3}',ident):raise ValueError('Invalid activity identifier')
 r,day,i=map(int,ident.split('-'));events=route_events(d,r,day)
 if not 0<=i<len(events):raise ValueError('Unknown stop')
 return r,day,i,events[i]

def validate_patch(p,complete=False):
 if not isinstance(p,dict) or not set(p)<=set(FIELDS) or (complete and set(p)!=set(FIELDS)) or any(not isinstance(v,str) or len(v)>6000 for v in p.values()):raise ValueError('Invalid activity patch')
 p=dict(p)
 if p.get('url') and not re.match(r'^https?://',p['url']):p['url']=''
 return p

def validate_request(req,d):
 if not isinstance(req,dict):raise ValueError('Invalid request')
 ident=req.get('id','');prompt=req.get('prompt','');cur=req.get('current',{})
 r,day,i,event=parse_id(d,ident)
 if not isinstance(prompt,str) or not 1<=len(prompt)<=3000:raise ValueError('Invalid edit prompt')
 if not isinstance(cur,dict):raise ValueError('Invalid stop context')
 if type(req.get('copyItinerary',False)) is not bool:raise ValueError('Invalid copy mode')
 cur={f:str(cur.get(f,d.get('edits',{}).get(ident,{}).get(f,event.get(f,''))))[:6000] for f in FIELDS}
 return ident,prompt,cur

def copy_route(d,req,ident):
 r,day,i,_=parse_id(d,ident);src=d['variants'][r];new_index=len(d['variants'])
 if new_index>9999:raise ValueError('Too many itineraries')
 name=req.get('copyName','')
 if not isinstance(name,str) or len(name)>120:raise ValueError('Invalid itinerary name')
 name=name.strip() or src['name'][:105]+' — copy';names={v['name'].casefold() for v in d['variants']};unique=name;n=2
 while unique.casefold() in names:
  suffix=f' ({n})';unique=name[:120-len(suffix)]+suffix;n+=1
 request_id=req.get('requestId','')
 if not isinstance(request_id,str) or not re.fullmatch(r'[a-zA-Z0-9-]{8,100}',request_id):raise ValueError('Invalid copy request ID')
 browser=req.get('localEdits',{})
 if not isinstance(browser,dict) or len(browser)>500:raise ValueError('Invalid local edits')
 # Copy all source route overlays, then apply the explicitly included browser-only overlays.
 edits=d.setdefault('edits',{});overlays={k:copy.deepcopy(v) for k,v in edits.items() if k.startswith(f'{r}-')}
 for k,p in browser.items():
  rr,_,_,_=parse_id(d,k)
  if rr!=r:raise ValueError('Copy may include only source itinerary edits')
  overlays[k]={**overlays.get(k,{}),**validate_patch(p)}
 v=copy.deepcopy(src);v.update(name=unique,tag='Custom copy',baseRoute=src.get('baseRoute',r),copiedFrom=src['name'],copyRequestId=request_id)
 v['desc']=src['desc'] # keep route summary and city order
 d['variants'].append(v)
 for k,p in overlays.items():
  _,dd,ii,_=parse_id(d,k);edits[f'{new_index}-{dd}-{ii}']=copy.deepcopy(p)
 orders=d.setdefault('activityOrders',{})
 for dd in range(len(src['order'])):
  k=f'{r}-{dd}'
  if k in orders:orders[f'{new_index}-{dd}']=copy.deepcopy(orders[k])
 for k,order in validate_orders(d,r,req.get('localOrders',{})).items():orders[f'{new_index}-{k.split('-')[1]}']=order
 return f'{new_index}-{day}-{i}' 

def validate_orders(d,r,orders):
 if not isinstance(orders,dict) or len(orders)>11:raise ValueError('Invalid day orders')
 out={}
 for k,v in orders.items():
  if not re.fullmatch(r'\d{1,4}-\d{1,2}',k):raise ValueError('Invalid day key')
  rr,day=map(int,k.split('-'))
  if rr!=r:raise ValueError('Order belongs to another route')
  n=len(route_events(d,r,day))
  if not isinstance(v,list) or any(type(i) is not int or not 0<=i<n for i in v) or len(set(v))!=len(v):raise ValueError('Invalid activity order')
  out[k]=v.copy()
 return out

def apply_order(req):
 h,m,d=load_html();ident=req.get('id');r,day,i,_=parse_id(d,ident)
 if req.get('route')!=r or req.get('day')!=day or type(req.get('copyItinerary',False)) is not bool:raise ValueError('Route or day mismatch')
 order=validate_orders(d,r,{f'{r}-{day}':req.get('order')})[f'{r}-{day}']
 if req.get('copyItinerary'):
  if any(v.get('copyRequestId')==req.get('requestId') for v in d['variants'] if v.get('copyRequestId')):return
  new=copy_route(d,req,ident);r=int(new.split('-')[0])
 d.setdefault('activityOrders',{})[f'{r}-{day}']=order
 serialized=json.dumps(d,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
 P.write_text(h[:m.start(2)]+serialized+h[m.end(2):],encoding='utf-8')
 print('Saved order',r,day)

def call_model(prompt,cur):
 key=os.environ.get('OPENAI_API_KEY');model=os.environ.get('OPENAI_MODEL') or 'gpt-4.1-mini'
 if not key:raise ValueError('Add OPENAI_API_KEY to GitHub Actions secrets')
 schema={'type':'object','properties':{f:{'type':'string'} for f in FIELDS},'required':FIELDS,'additionalProperties':False}
 payload={'model':model,'input':[{'role':'system','content':'You edit one activity in a family Japan travel itinerary for January 1–11, 2027. Preserve all unrequested fields. Return only a complete JSON object of the allowed text fields. Do not invent ratings, prices, photos, business hours, reservations, locations, URLs, or verified travel times. You have no live research access in this workflow. Mark new facts unknown and clearly say what needs verification. Prefer walk or transit, no hostels/shared bathrooms, one professional mother–daughter photoshoot total, family together, Kyoto before Osaka in main route. Keep time format HH:MM–HH:MM. Never output executable code or secrets.'},{'role':'user','content':json.dumps({'current_activity':cur,'requested_change':prompt},ensure_ascii=False)}],'text':{'format':{'type':'json_schema','name':'activity_edit','strict':True,'schema':schema}},'max_output_tokens':3500}
 request=urllib.request.Request('https://api.openai.com/v1/responses',data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},method='POST')
 with urllib.request.urlopen(request,timeout=150) as response:result=json.load(response)
 txt=''.join(c.get('text','') for item in result.get('output',[]) if item.get('type')=='message' for c in item.get('content',[]) if c.get('type')=='output_text')
 if not txt:raise ValueError('No structured edit returned by model')
 return json.loads(txt)
def apply_edit(req,edited=None):
 h,m,d=load_html();ident,prompt,cur=validate_request(req,d)
 if req.get('copyItinerary') and any(v.get('copyRequestId')==req.get('requestId') for v in d['variants'] if v.get('copyRequestId')):
  print('Copy already saved; no duplicate created');return
 # Validate copy first in memory. No HTML is written if validation or model call fails.
 if req.get('copyItinerary'):ident=copy_route(d,req,ident)
 patch=validate_patch(edited if edited is not None else call_model(prompt,cur),complete=True)
 d.setdefault('edits',{})[ident]=patch
 # Escape markup so no text value can close the JSON script element.
 serialized=json.dumps(d,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
 P.write_text(h[:m.start(2)]+serialized+h[m.end(2):],encoding='utf-8')
 print('Validated and saved activity',ident)
if __name__=='__main__':
 event=json.loads(pathlib.Path(os.environ['GITHUB_EVENT_PATH']).read_text());req=json.loads(event['inputs']['request'])
 if req.get('type')=='hotel_refresh':
  from refresh_hotels import apply_refresh
  apply_refresh(req)
 elif req.get('type')=='activity_order':apply_order(req)
 elif req.get('type')=='auto_hotel_refresh':
  from auto_refresh import refresh
  refresh(req)
 else:apply_edit(req, req.get('manual'))
