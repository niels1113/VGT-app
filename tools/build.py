"""Zoekt voor elk woord uit de app het gebaar op in de VGT Signbank,
analyseert de video met MediaPipe en schrijft data/signs.json.
Video's zelf worden NIET opgeslagen; enkel het adres en de bewegingsdata.
Draait als GitHub Action (zie .github/workflows/build.yml)."""
import json, os, re, sys, time, html, tempfile, urllib.request, urllib.parse
import cv2, mediapipe as mp
from mediapipe.tasks import python as mpt
from mediapipe.tasks.python import vision

HEADERS = None
BASE = "https://vlaamsegebarentaal.be/signbank"
UA = {"User-Agent": "Mozilla/5.0 (persoonlijke VGT-leerapp; 1 verzoek per seconde)"}
OUT = "data/signs.json"
REPORT = "data/report.json"


def get(url, binary=False):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    time.sleep(1.0)  # vriendelijk voor de server
    return data if binary else data.decode("utf-8", "replace")


def words_from_app():
    src = open("index.html", encoding="utf-8").read()
    words = []
    for block in re.findall(r'w:\[(\[.*?\])\]\}', src):
        for w in re.findall(r'\["([^"]+)","[^"]*"\]', block):
            if w not in words:
                words.append(w)
    extra = "tools/extra_words.txt"
    if os.path.exists(extra):
        for line in open(extra, encoding="utf-8"):
            w = line.strip()
            if w and not w.startswith("#") and w not in words:
                words.append(w)
    return words


def clean(s):
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def search(word):
    q = urllib.parse.quote(word)
    page = get(f"{BASE}/signs/search/?keyword={q}")
    page = page.replace("<!--", "").replace("-->", "")
    global HEADERS
    if HEADERS is None:
        HEADERS = [clean(h) for h in re.findall(r"(?s)<th[^>]*>(.*?)</th>", page)]
    rows = []
    for tr in re.findall(r"(?s)<tr.*?</tr>", page):
        m = re.search(r'href="[^"]*?/dictionary/gloss/(\d+)/?"[^>]*>(.*?)</a>', tr, re.S)
        if not m:
            continue
        cells = [clean(c) for c in re.findall(r"(?s)<td[^>]*>(.*?)</td>", tr)]
        rows.append({"id": m.group(1), "gloss": clean(m.group(2)), "cells": cells})
    return rows


def score(word, row):
    w = word.lower()
    sc = 0
    for c in row["cells"]:
        parts = [p.strip().lower() for p in re.split(r"[,;/]", c)]
        if w in parts:
            sc += 10
            break
    if any(c.strip() == "Ja" for c in row["cells"]):
        sc += 5
    if any("Vlaanderen" in c for c in row["cells"]):
        sc += 2
    g = row["gloss"].upper()
    base = re.sub(r"-[A-Z]$", "", g)
    if base == w.upper().replace(" ", "-") or base == w.upper():
        sc += 3
    if g.endswith("-A"):
        sc += 1
    return sc


# Andere zoektermen voor woorden die de Signbank anders noteert
ALIASES = {
    "dank je": ["dank", "bedanken", "dank u"],
    "alsjeblieft": ["alstublieft", "a.u.b.", "aub"],
    "oké": ["ok", "oke", "okay", "in orde"],
    "naar huis": ["huis", "naar huis gaan"],
    "ik hou van jou": ["houden van", "graag zien", "liefde"],
}


def parse_details(page):
    page = re.sub(r"(?s)<!--.*?-->", "", page)
    page = re.sub(r"(?s)<(script|style).*?</\1>", "", page)
    det = {}
    for th, td in re.findall(r"(?s)<th[^>]*>(.*?)</th>\s*<td[^>]*>(.*?)</td>", page):
        k, v = clean(th).rstrip(":"), clean(td)
        if k and v and len(k) < 60 and len(v) < 300 and k not in det:
            det[k] = v
    for lab, val in re.findall(r'(?s)<label[^>]*>(.*?)</label>\s*(?:</[^>]+>\s*)*<[^>]+>(.*?)<', page):
        k, v = clean(lab).rstrip(":"), clean(val)
        if k and v and len(k) < 60 and len(v) < 300 and k not in det:
            det[k] = v
    return det


def gloss_page(gid):
    return get(f"{BASE}/dictionary/gloss/{gid}/")


def video_url(gid, page=None):
    page = page or get(f"{BASE}/dictionary/gloss/{gid}/")
    m = re.search(r'(/dictionary/protected_media/glossvideo/[^"\']+?\.mp4)', page)
    return BASE + m.group(1) if m else None


# ---------- features (identiek aan frameFeat() in index.html) ----------
def r3(v):
    return round(v * 1000) / 1000


def frame_feat(hands, pose, W, H):
    cx, cy, sc = W / 2, H * 0.55, W * 0.3
    if pose and len(pose) > 12:
        l, r = pose[11], pose[12]
        d = (((l.x - r.x) * W) ** 2 + ((l.y - r.y) * H) ** 2) ** 0.5
        if d > 8:
            cx, cy, sc = (l.x + r.x) / 2 * W, (l.y + r.y) / 2 * H, d
    slots = [None, None]
    hs = sorted([(lm, lm[0].x * W) for lm in hands[:2]], key=lambda t: t[1])
    if len(hs) == 2:
        slots = [hs[0][0], hs[1][0]]
    elif len(hs) == 1:
        slots[0 if hs[0][1] < cx else 1] = hs[0][0]
    out = []
    for lm in slots:
        if lm is None:
            out.append(None)
            continue
        pts = [(p.x * W, p.y * H) for p in lm]
        w = pts[0]
        size = ((pts[9][0] - w[0]) ** 2 + (pts[9][1] - w[1]) ** 2) ** 0.5 or 1
        s = []
        for i in range(1, 21):
            s += [r3((pts[i][0] - w[0]) / size), r3((pts[i][1] - w[1]) / size)]
        pc = ((pts[0][0] + pts[9][0]) / 2, (pts[0][1] + pts[9][1]) / 2)
        out.append({"s": s, "p": [r3((pc[0] - cx) / sc), r3((pc[1] - cy) / sc)]})
    return out


def analyze(path):
    hand = vision.HandLandmarker.create_from_options(vision.HandLandmarkerOptions(
        base_options=mpt.BaseOptions(model_asset_path="models/hand.task"),
        running_mode=vision.RunningMode.VIDEO, num_hands=2))
    pose = vision.PoseLandmarker.create_from_options(vision.PoseLandmarkerOptions(
        base_options=mpt.BaseOptions(model_asset_path="models/pose.task"),
        running_mode=vision.RunningMode.VIDEO, num_poses=1))
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    n = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    dur = n / fps if n else 4
    step = max(0.1, dur / 120)
    frames, nxt, i = [], 0.0, 0
    while True:
        ok, img = cap.read()
        if not ok:
            break
        t = i / fps
        i += 1
        if t + 1e-6 < nxt:
            continue
        nxt += step
        H, W = img.shape[:2]
        mi = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        ts = int(t * 1000)
        hr = hand.detect_for_video(mi, ts)
        pr = pose.detect_for_video(mi, ts)
        pl = pr.pose_landmarks[0] if pr.pose_landmarks else None
        frames.append(frame_feat(hr.hand_landmarks or [], pl, W, H))
    cap.release()
    hand.close()
    pose.close()
    return frames, round(dur, 3)


def main():
    force = "--force" in sys.argv
    os.makedirs("data", exist_ok=True)
    data = json.load(open(OUT)) if os.path.exists(OUT) else {}
    report = {"gevonden": [], "niet_gevonden": [], "fouten": []}
    for w in words_from_app():
        if w in data and not force:
            report["gevonden"].append(w)
            if not data[w].get("cells2"):
                try:
                    for term in [w] + ALIASES.get(w, []):
                        hit = [r for r in search(term) if r["id"] == data[w]["id"]]
                        if hit:
                            data[w]["cells2"] = hit[0]["cells"]
                            break
                except Exception as e:
                    report["fouten"].append({"woord": w, "fout": "cells: " + str(e)[:200]})
            continue
        try:
            best, cands = None, []
            for term in [w] + ALIASES.get(w, []):
                rows = search(term)
                cands += [r["gloss"] for r in rows[:4]]
                if rows:
                    b = max(rows, key=lambda r: score(term, r))
                    if score(term, b) >= 10:
                        best = b
                        break
            if not best:
                report["niet_gevonden"].append({"woord": w, "kandidaten": cands[:10]})
                continue
            pg = gloss_page(best["id"])
            url = video_url(best["id"], pg)
            if not url:
                report["niet_gevonden"].append({"woord": w, "gloss": best["gloss"], "reden": "geen video"})
                continue
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
                f.write(get(url, binary=True))
                tmp = f.name
            frames, dur = analyze(tmp)
            os.unlink(tmp)
            data[w] = {"url": url, "gloss": best["gloss"], "id": best["id"], "dur": dur, "frames": frames, "cells2": best["cells"]}
            report["gevonden"].append(w)
            print("OK", w, best["gloss"], len(frames), flush=True)
            json.dump(data, open(OUT, "w"), ensure_ascii=False, separators=(",", ":"))
        except Exception as e:
            report["fouten"].append({"woord": w, "fout": str(e)[:300]})
            print("FOUT", w, e, flush=True)
    json.dump(data, open(OUT, "w"), ensure_ascii=False, separators=(",", ":"))
    report["kolommen"] = HEADERS
    json.dump(report, open(REPORT, "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
