#!/usr/bin/env python3
import datetime as dt, json, os, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
TOPIC_NAMES=['heracleion', 'cahokia', 'great-zimbabwe', 'nan-madol', 'skara-brae', 'derinkuyu', 'akrotiri', 'catalhoyuk', 'hattusa', 'angkor', 'leptis-magna', 'mohenjo-daro', 'petra', 'tikal', 'machu-picchu', 'persepolis', 'carthage', 'knossos', 'ur', 'babylon', 'teotihuacan', 'mesa-verde', 'ani', 'gobekli-tepe']

def files():
    out=[ROOT/f"{x}.json" for x in TOPIC_NAMES if (ROOT/f"{x}.json").exists()]
    if not out: raise SystemExit("No V4 topics found")
    return out

def used():
    p=ROOT/"used_topics.json"
    if not p.exists(): return []
    try:
        v=json.loads(p.read_text(encoding="utf-8"))
        return v if isinstance(v,list) else []
    except Exception: return []

def valid(p):
    d=json.loads(p.read_text(encoding="utf-8"))
    for k in ("title","hook_text","description","scenes"):
        if not d.get(k): raise SystemExit(f"{p.name} missing {k}")
    if not 6 <= len(d["scenes"]) <= 16: raise SystemExit(f"{p.name} scenes must be 6-16")
    return d

def main():
    req=sys.argv[1] if len(sys.argv)>1 else os.getenv("VIDEO_TOPIC","auto")
    fs=files()
    if req!="auto":
        req=req.removesuffix(".json")
        selected=next((p for p in fs if p.stem==req),None)
        if not selected: raise SystemExit(f"Unknown topic: {req}")
    else:
        seen={str(x).strip().lower() for x in used()}
        available=[p for p in fs if p.stem.lower() not in seen]
        if not available:
            raise SystemExit("All topics have been used. Add new topics before rendering more videos.")
        day=dt.datetime.now(dt.timezone.utc).date().toordinal()
        selected=available[day % len(available)]
    d=valid(selected)
    Path("selected_topic.txt").write_text(selected.stem+"\n",encoding="utf-8")
    Path("selection.json").write_text(json.dumps({"slug":selected.stem,"title":d["title"],"date_utc":str(dt.datetime.now(dt.timezone.utc).date()),"available":len(fs)},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("SELECTED:",selected.stem)

if __name__=="__main__": main()
