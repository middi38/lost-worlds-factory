#!/usr/bin/env python3
import asyncio, json, os, random, re, subprocess, sys, time, urllib.parse, urllib.request
from pathlib import Path

FPS=30
PAD=0.18
FORMATS={"short":(1080,1920),"long":(1920,1080)}
OFFLINE=os.environ.get("FACTORY_OFFLINE")=="1"
_KOKORO={}
def log(x): print(x,flush=True)
def run(cmd,cwd=None):
    cmd=[str(x) for x in cmd]; log("$ "+" ".join(cmd)[:260]); subprocess.run(cmd,check=True,cwd=cwd)
def duration(p):
    r=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=nw=1:nk=1",str(p)],capture_output=True,text=True,check=True)
    return float(r.stdout.strip())
def validate(s):
    assert s.get("scenes") and 6 <= len(s["scenes"]) <= 16, "6-16 scenes required"
    assert s.get("format","short") in FORMATS
    for i,x in enumerate(s["scenes"]):
        assert x.get("text") and x.get("image"), f"scene {i+1} missing text/image"
def kokoro(text,voice,speed,out):
    import numpy as np, soundfile as sf
    from kokoro import KPipeline
    lang=voice[0]
    if lang not in _KOKORO: _KOKORO[lang]=KPipeline(lang_code=lang,repo_id="hexgrad/Kokoro-82M")
    a=[]
    for r in _KOKORO[lang](text,voice=voice,speed=speed):
        x=getattr(r,"audio",None)
        if x is None: x=r[2]
        if hasattr(x,"cpu"): x=x.cpu().numpy()
        a.append(np.asarray(x,dtype="float32"))
    if not a: raise RuntimeError("Kokoro produced no audio")
    sf.write(str(out),np.concatenate(a),24000)
async def edge(text,voice,rate,out):
    import edge_tts
    for n in range(5):
        try:
            await edge_tts.Communicate(text,voice,rate=rate).save(str(out))
            if out.exists() and out.stat().st_size>1000:return
        except Exception as e: log(f"edge retry {n+1}: {e}")
        await asyncio.sleep(4*(n+1))
    raise RuntimeError("TTS failed")
async def voice(text,s,base):
    if OFFLINE:
        o=base.with_suffix(".mp3"); run(["ffmpeg","-y","-f","lavfi","-i",f"sine=frequency=220:duration={max(2,len(text.split())*.35)}","-q:a","4",o]); return o
    if s.get("voice_engine","kokoro")=="kokoro":
        o=base.with_suffix(".wav")
        try: kokoro(text,s.get("voice","af_heart"),float(s.get("speed",.97)),o); return o
        except Exception as e: log("Kokoro fallback: "+str(e))
    o=base.with_suffix(".mp3"); await edge(text,s.get("edge_voice","en-US-AndrewMultilingualNeural"),s.get("rate","-3%"),o); return o
def download(url,headers,out,tries=4):
    for n in range(tries):
        try:
            req=urllib.request.Request(url,headers=headers)
            with urllib.request.urlopen(req,timeout=180) as r: data=r.read(); ct=r.headers.get("Content-Type","")
            if ct.startswith("image") and len(data)>20000: out.write_bytes(data); return True
        except Exception as e: log(f"image retry {n+1}: {e}")
        time.sleep(8*(n+1))
    return False
def image(prompt,w,h,seed,out,token):
    if OFFLINE:return False
    q=urllib.parse.quote(prompt,safe=""); p=f"width={w}&height={h}&seed={seed}&model=flux&nologo=true"
    ua={"User-Agent":"lost-worlds-factory/3.0"}
    if token and download(f"https://gen.pollinations.ai/image/{q}?{p}",{**ua,"Authorization":f"Bearer {token}"},out): return True
    return download(f"https://image.pollinations.ai/prompt/{q}?{p}",ua,out,5)
def placeholder(w,h,out): run(["ffmpeg","-y","-f","lavfi","-i",f"color=c=0x17130f:s={w}x{h}","-frames:v","1",out])
def clip(img,a,d,w,h,i,out):
    F=max(1,round(d*FPS))
    moves=[(f"1+0.13*on/{F}","(iw-iw/zoom)/2","(ih-ih/zoom)/2"),("1.12",f"(iw-iw/zoom)*on/{F}","(ih-ih/zoom)/2"),("1.12",f"(iw-iw/zoom)*(1-on/{F})","(ih-ih/zoom)/2"),("1.12","(iw-iw/zoom)/2",f"(ih-ih/zoom)*on/{F}")]
    z,x,y=moves[i%len(moves)]
    vf=(f"[0:v]scale={w*2}:{h*2}:force_original_aspect_ratio=increase,crop={w*2}:{h*2},"
        f"eq=contrast=1.06:saturation=.94:gamma=.98,unsharp=5:5:.45,"
        f"zoompan=z='{z}':x='{x}':y='{y}':d={F}:s={w}x{h}:fps={FPS},vignette=PI/5,noise=alls=4:allf=t+u,format=yuv420p[v];"
        f"[1:a]apad=pad_dur={PAD},highpass=f=70,lowpass=f=15500,loudnorm=I=-16:TP=-1.5:LRA=9,aresample=44100[a]")
    run(["ffmpeg","-y","-loop","1","-i",img,"-i",a,"-filter_complex",vf,"-map","[v]","-map","[a]","-t",f"{d:.3f}","-c:v","libx264","-preset","veryfast","-crf","19","-r",FPS,"-c:a","aac","-b:a","192k",out])
def at(t):
    c=round(max(0,t)*100); return f"{c//360000}:{(c//6000)%60:02d}:{(c//100)%60:02d}.{c%100:02d}"
def events(text,start,d):
    words=text.split(); chunks=[]; cur=[]
    for x in words:
        cur.append(x)
        if len(cur)>=3 or re.search(r"[,.!?;:]$",x): chunks.append(" ".join(cur));cur=[]
    if cur:chunks.append(" ".join(cur))
    total=sum(len(x)+1 for x in chunks) or 1;t=start;out=[]
    for x in chunks:
        dd=d*(len(x)+1)/total;out.append((t,t+dd,"Sub",x.upper()));t+=dd
    return out
def ass(path,ev,w,h,fmt):
    fs,mv,hfs,hmv=(78,540,66,250) if fmt=="short" else (58,90,60,80)
    L=["[Script Info]","ScriptType: v4.00+",f"PlayResX: {w}",f"PlayResY: {h}","WrapStyle: 0","ScaledBorderAndShadow: yes","",
    "[V4+ Styles]","Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
    f"Style: Sub,DejaVu Sans,{fs},&H00FFFFFF,&H000000FF,&H00000000,&H70000000,-1,0,0,0,100,100,0,0,1,5,2,2,70,70,{mv},1",
    f"Style: Hook,DejaVu Sans,{hfs},&H0000D7FF,&H000000FF,&H00000000,&H70000000,-1,0,0,0,100,100,0,0,1,5,2,8,70,70,{hmv},1","",
    "[Events]","Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    for s,e,st,tx in ev:L.append(f"Dialogue: 0,{at(s)},{at(e)},{st},,0,0,0,,{tx.replace('{','(').replace('}',')')}")
    path.write_text("\n".join(L)+"\n",encoding="utf8")
async def main():
    if len(sys.argv)<2:sys.exit("python factory.py video.json")
    p=Path(sys.argv[1]);s=json.loads(p.read_text(encoding="utf8"));validate(s)
    fmt=s.get("format","short");w,h=FORMATS[fmt];slug=p.stem;work=Path("work")/slug;work.mkdir(parents=True,exist_ok=True);out=Path("output");out.mkdir(exist_ok=True)
    style=s.get("image_style","cinematic historical documentary, photorealistic, historically accurate, natural light, 35mm lens, atmospheric depth, realistic skin and fabric, no text, no logo, no watermark")
    seed=int(s.get("seed",1000));token=os.getenv("POLLINATIONS_TOKEN","").strip();ev=[];clips=[];t=0;first=0
    for i,sc in enumerate(s["scenes"]):
        log(f"=== scene {i+1}/{len(s['scenes'])} ===");im=work/f"i{i:03}.jpg";c=work/f"c{i:03}.mp4"
        a=await voice(sc["text"],s,work/f"a{i:03}");ad=duration(a)
        prompt=f"{sc['image']}, {style}, vertical composition, subject centered with safe space for subtitles"
        if not image(prompt,w,h,seed+i,im,token):placeholder(w,h,im)
        d=ad+PAD;clip(im,a,d,w,h,i,c);clips.append(c.name);ev+=events(sc["text"],t,ad);t+=d
        if i==0:first=t
    if s.get("hook_text"):ev.insert(0,(0,min(first,2.6),"Hook",s["hook_text"].upper()))
    (work/"list.txt").write_text("".join(f"file '{x}'\n" for x in clips),encoding="utf8")
    run(["ffmpeg","-y","-f","concat","-safe","0","-i","list.txt","-c","copy","joined.mp4"],cwd=work);ass(work/"subs.ass",ev,w,h,fmt)
    final=(out/f"{slug}.mp4").resolve();mus=sorted(Path("music").glob("*.mp3")) if Path("music").exists() else []
    if mus:
        m=random.Random(seed).choice(mus).resolve();vol=float(s.get("music_volume",.10))
        run(["ffmpeg","-y","-i","joined.mp4","-stream_loop","-1","-i",m,"-filter_complex",f"[0:v]ass=subs.ass[v];[1:a]volume={vol}[m];[0:a][m]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.2:LRA=8[a]","-map","[v]","-map","[a]","-c:v","libx264","-preset","veryfast","-crf","19","-c:a","aac","-b:a","192k","-movflags","+faststart",final],cwd=work)
    else:run(["ffmpeg","-y","-i","joined.mp4","-vf","ass=subs.ass","-c:v","libx264","-preset","veryfast","-crf","19","-c:a","aac","-b:a","192k","-movflags","+faststart",final],cwd=work)
    meta=["TITLE:",s.get("title",""),"","DESCRIPTION:",s.get("description",""),"","TAGS:",", ".join(s.get("tags",[])),"","DISCLOSURE: AI-generated/recreated visuals. Follow YouTube's current altered/synthetic content disclosure rules when applicable."]
    (out/f"{slug}_metadata.txt").write_text("\n".join(meta),encoding="utf8")
    log(f"DONE {final} {duration(final):.1f}s")
if __name__=="__main__":asyncio.run(main())
