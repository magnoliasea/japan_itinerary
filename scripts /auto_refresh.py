"""Refresh shortlisted Expedia properties using approved Travel Redirect credentials."""
import os,base64,urllib.request,urllib.parse,json,uuid,datetime,math
from edit_atlas import load_html, P
from refresh_hotels import GROUPS,hotelid

def money(p):
    if not isinstance(p,dict):return None
    c=p.get('Currency') or p.get('CurrencyCode');v=p.get('Value',p.get('Amount'))
    if c!='USD' or isinstance(v,bool):return None
    try:v=float(v)
    except (ValueError,TypeError):return None
    return v if math.isfinite(v) and 0<v<=100000 else None

def extract(payload,ids):
    if not isinstance(payload,dict) or payload.get('Errors') or not isinstance(payload.get('Hotels'),list):raise ValueError('Expedia did not return a valid hotel list')
    result={}
    for h in payload['Hotels']:
        hid=str(h.get('Id',''))
        if hid not in ids:continue
        prices=[]
        for room in h.get('RoomTypes') or []:
            for plan in [room]+(room.get('RatePlans') or []):
                price=plan.get('Price') or {}
                val=money(price.get('TotalPriceWithHotelFees'))
                if val is not None:prices.append(val)
        if prices:result[hid]=min(prices)
    return result

def refresh(req,payload=None):
    html,m,d=load_html(); k=req.get('stay')
    if k not in GROUPS:raise ValueError('Invalid stay')
    a,b=k.split('-');ids={hotelid(h) for h in d['hotels'][k]}-{''}; adults=2 if k=='10-11' else 4
    if not ids:raise ValueError('No shortlisted property IDs')
    if payload is None:
        key=os.environ.get('EXPEDIA_API_KEY');user=os.environ.get('EXPEDIA_API_USERNAME');password=os.environ.get('EXPEDIA_API_PASSWORD')
        if not all([key,user,password]):raise ValueError('Approved Expedia Travel Redirect credentials are not configured. No prices changed.')
        query=urllib.parse.urlencode({'ecomHotelIds':','.join(sorted(ids)),'checkIn':'2027-01-'+a,'checkOut':'2027-01-'+b,'room1.adults':adults,'currency':'USD','locale':'en_US','allRoomTypes':'true','contentDetails':'low'})
        auth=base64.b64encode((user+':'+password).encode()).decode()
        r=urllib.request.Request('https://apim.expedia.com/hotels/listings?'+query,headers={'Accept':'application/vnd.exp-hotel.v3+json','Key':key,'Authorization':'Basic '+auth,'Partner-Transaction-Id':str(uuid.uuid4())})
        with urllib.request.urlopen(r,timeout=75) as f:payload=json.load(f)
    result=extract(payload,ids)
    if not result:raise ValueError('No recognized USD whole-stay totals including hotel fees. Previous prices retained; inspect provider response schema/availability.')
    stamp=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
    for h in d['hotels'][k]:
        hid=hotelid(h)
        if hid not in ids:continue
        if hid in result:h.update(price=result[hid],quoteStatus='quoted',quoteCheckedAt=stamp,quoteSource='Expedia Travel Redirect API',quoteNote='Lowest returned whole-stay USD offer with hotel fees; confirm private bathroom and exact room category before booking.')
        else:h.update(price=None,quoteStatus='not_found',quoteCheckedAt=stamp,quoteSource='Expedia Travel Redirect API',quoteNote='No recognized inclusive USD total returned; not proof of sold out.')
    d.setdefault('hotelRefresh',{})[k]=stamp
    serialized=json.dumps(d,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    P.write_text(html[:m.start(2)]+serialized+html[m.end(2):],encoding='utf-8')
    print('Refreshed',len(result),'shortlisted hotels for',k)
