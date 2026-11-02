# Verkent de structuur van het VGT-woordenboek (eenmalig, ter debug).
import urllib.request, re, json, sys
UA = {"User-Agent": "Mozilla/5.0 (VGT-leerapp, persoonlijk gebruik)"}
def get(url):
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, dict(r.headers), r.read(400000).decode("utf-8", "replace")
    except Exception as e:
        code = getattr(e, "code", None)
        body = ""
        try: body = e.read(20000).decode("utf-8","replace")
        except Exception: pass
        return code, {"error": str(e)}, body
out = {}
urls = [
 "https://woordenboek.vlaamsegebarentaal.be/",
 "https://woordenboek.vlaamsegebarentaal.be/search?query=hallo",
 "https://woordenboek.vlaamsegebarentaal.be/zoeken?q=hallo",
 "https://woordenboek.vlaamsegebarentaal.be/gloss/HALLO-A-16601",
 "https://vlaamsegebarentaal.be/signbank/dictionary/search/?query=hallo",
 "https://vlaamsegebarentaal.be/signbank/dictionary/gloss/16601/",
 "https://vlaamsegebarentaal.be/signbank/dictionary/protected_media/glossvideo/HA/HALLO-A-16601.mp4",
]
for u in urls:
    st, h, body = get(u)
    out[u] = {"status": st, "headers": {k: v for k, v in h.items() if k.lower() in ("content-type","access-control-allow-origin","location","error","content-length")},
              "mp4": sorted(set(re.findall(r"[\w/\-\.:]*glossvideo[\w/\-\.]*\.mp4", body)))[:20],
              "links": sorted(set(re.findall(r'(?:href|src|action)="([^"]{1,200})"', body)))[:80],
              "scripts_api": sorted(set(re.findall(r'["\'](/[^"\']*(?:api|search|gloss|zoek)[^"\']*)["\']', body)))[:60],
              "snippet": body[:1500] if "mp4" not in u else ""}
json.dump(out, open("tools/probe.json", "w"), indent=1, ensure_ascii=False)
