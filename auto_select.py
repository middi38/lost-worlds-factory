#!/usr/bin/env python3
import argparse, datetime as dt, json, os, shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parent
TOPICS=ROOT/'topics'

def catalog():
    files=sorted(TOPICS.glob('*.json'))
    if not files: raise SystemExit('No topic JSON files found in topics/')
    return files

def choose(files, requested):
    if requested and requested != 'auto':
        p=TOPICS/f'{requested}.json'
        if not p.exists(): raise SystemExit(f'Unknown topic: {requested}')
        return p
    # Stable daily rotation. A rerun on the same UTC day creates the same topic;
    # the next day automatically advances to the next topic.
    day=dt.datetime.now(dt.timezone.utc).date().toordinal()
    return files[day % len(files)]

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--topic',default=os.getenv('VIDEO_TOPIC','auto'))
    ap.add_argument('--out',default='selected.json')
    args=ap.parse_args()
    files=catalog(); src=choose(files,args.topic)
    data=json.loads(src.read_text(encoding='utf-8'))
    required=['title','hook_text','description','scenes']
    missing=[k for k in required if not data.get(k)]
    if missing: raise SystemExit(f'{src}: missing {missing}')
    if not 6 <= len(data['scenes']) <= 16: raise SystemExit(f'{src}: scenes must be 6-16')
    shutil.copyfile(src,args.out)
    info={'slug':src.stem,'source':str(src),'title':data['title'],'date_utc':str(dt.datetime.now(dt.timezone.utc).date()),'catalog_size':len(files)}
    Path('selection.json').write_text(json.dumps(info,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(info,ensure_ascii=False))
if __name__=='__main__': main()
