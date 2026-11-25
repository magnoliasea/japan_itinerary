"""Validate one user-approved activity edit; modify only embedded JSON, never executable HTML."""
import os,json,re,pathlib,urllib.request,sys
P=pathlib.Path('index.html')
FIELDS=['time','name','place','travel','hours','price','desc','tip','souvenir','options','url']
def load_html():
 h=P.read_text(encoding='utf-8');m=re.search(r'(<script id="data" type="application/json">)(.*?)(</script>)',h,re.S)
 if not m:raise ValueError('Cannot find embedded itinerary data')
 return h,m,json.loads(m[2])
def validate_request(req,d):
 if not isinstance(req,dict):raise ValueError('Invalid request')
 ident=req.get('id','');prompt=req.get('prompt','');cur=req.get('current',{})
 if not re.fullmatch(r'\d{1,2}-\d{1,2}-\d{1,2}',ident):raise ValueError('Invalid activity identifier')
 r,day,i=map(int,ident.split('-'))
 if not (0<=r<len(d['variants']) and 0<=day<len(d['variants'][r]['order'])):raise ValueError('Unknown route/day')
 k=d['variants'][r]['order'][day];events=(d['ultimate'] if r==4 else d['days'])[k]['events']
 if not 0<=i<len(events):raise ValueError('Unknown stop')
 if not isinstance(prompt,str) or not 1<=len(prompt)<=3000:raise ValueError('Invalid edit prompt')
 if not isinstance(cur,dict):raise ValueError('Invalid stop context')
 cur={f:str(cur.get(f,events[i].get(f,'')))[:6000] for f in FIELDS}
 # Only data fields can be changed. User controls the workflow trigger via scoped GitHub token.
 return ident,prompt,cur

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
 h,m,d=load_html();ident,prompt,cur=validate_request(req,d);patch=edited if edited is not None else call_model(prompt,cur)
 if not isinstance(patch,dict) or set(patch)!=set(FIELDS) or any(not isinstance(v,str) or len(v)>6000 for v in patch.values()):raise ValueError('Invalid model output')
 if patch['url'] and not re.match(r'^https?://',patch['url']):patch['url']=''
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
 else:apply_edit(req, req.get('manual'))
