import urllib.request, re, json, html
UA = {"User-Agent": "Mozilla/5.0 (VGT-leerapp, persoonlijk gebruik)"}
def get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
            return r.status, r.headers.get("content-type",""), r.read(3000000).decode("utf-8","replace")
    except Exception as e:
        b=""
        try: b=e.read(20000).decode("utf-8","replace")
        except Exception: pass
        return getattr(e,"code",None), str(e), b
out = {}
st, ct, js = get("https://woordenboek.vlaamsegebarentaal.be/js/app.8dc66aae.js")
out["appjs"] = {"status": st, "len": len(js),
  "urls": sorted(set(re.findall(r'https?://[a-zA-Z0-9\.\-/_:%\?=&]+', js)))[:80],
  "paths": sorted(set(re.findall(r'["`\'](/[a-zA-Z0-9_\-/]*(?:api|search|gloss|sign|video|zoek|lemma|dictionary)[a-zA-Z0-9_\-/\.]*)["`\']', js)))[:80],
  "ctx": [js[max(0,m.start()-200):m.start()+250] for m in re.finditer(r'search|zoek', js)][:12]}
for u in ["https://vlaamsegebarentaal.be/signbank/signs/search/?keyword=hallo",
          "https://vlaamsegebarentaal.be/signbank/signs/search/?search=hallo",
          "https://vlaamsegebarentaal.be/signbank/about/copyright/"]:
    st, ct, b = get(u)
    txt = re.sub(r"\s+"," ", html.unescape(re.sub(r"<[^>]+>"," ", re.sub(r"(?s)<(script|style).*?</\1>","",b))))
    out[u] = {"status": st, "glosslinks": sorted(set(re.findall(r'/dictionary/gloss/\d+/?', b)))[:20],
              "text": txt[:3000]}
json.dump(out, open("tools/probe.json","w"), indent=1, ensure_ascii=False)
