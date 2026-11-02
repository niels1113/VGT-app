import urllib.request, re, json
UA={"User-Agent":"Mozilla/5.0"}
def get(u):
    with urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=60) as r: return r.read().decode("utf-8","replace")
base="https://woordenboek.vlaamsegebarentaal.be/"
idx=get(base); out={}
js=re.findall(r'(js/[\w\.\-]+\.js)', idx)
allsrc=""
for j in js:
    if "legacy" in j: continue
    try: allsrc+=get(base+j)
    except Exception as e: out[j]=str(e)
out["api"]=sorted(set(re.findall(r'["`\']((?:https?:)?/{0,2}[\w\.\-/]*api[\w\-/\.\$\{\}]*)["`\']',allsrc)))[:80]
out["ctx"]=[allsrc[max(0,m.start()-250):m.start()+250] for m in re.finditer(r'baseURL|axios\.create|fetch\(|/api/|handshape|Handvorm|handvorm|location', allsrc)][:25]
json.dump(out,open("data/probe_js.json","w"),indent=1,ensure_ascii=False)
