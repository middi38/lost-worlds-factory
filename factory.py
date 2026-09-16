#!/usr/bin/env python3
"""
Lost Worlds Recreated - Video Factory
Kullanim: python factory.py pompeii.json
Cikti:    output/<ad>.mp4 ve output/<ad>_metadata.txt
"""
import asyncio
import json
import os
import random
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

FPS = 30
PAD = 0.35  # her sahnenin sonuna eklenen kisa sessizlik (saniye)
FORMATS = {"short": (1080, 1920), "long": (1920, 1080)}
OFFLINE = os.environ.get("FACTORY_OFFLINE") == "1"  # sadece yerel test icin


def log(msg):
    print(msg, flush=True)


def run(cmd, cwd=None):
    cmd = [str(c) for c in cmd]
    log("$ " + " ".join(cmd)[:250])
    subprocess.run(cmd, check=True, cwd=cwd)


def media_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True).stdout
    return float(out.strip())


# ---------- 1) SESLENDIRME ----------
_KOKORO = {}


def kokoro_voice(text, voice, speed, out):
    """Kokoro: ucretsiz, acik kaynak, cok dogal ses. CPU'da calisir."""
    import numpy as np
    import soundfile as sf
    from kokoro import KPipeline
    lang = voice[0]  # 'a' = Amerikan, 'b' = Ingiliz
    if lang not in _KOKORO:
        _KOKORO[lang] = KPipeline(lang_code=lang, repo_id="hexgrad/Kokoro-82M")
    parts = []
    for res in _KOKORO[lang](text, voice=voice, speed=speed):
        audio = getattr(res, "audio", None)
        if audio is None:
            audio = res[2]
        if hasattr(audio, "cpu"):
            audio = audio.cpu().numpy()
        parts.append(np.asarray(audio, dtype="float32"))
    if not parts:
        raise RuntimeError("Kokoro ses uretmedi")
    sf.write(str(out), np.concatenate(parts), 24000)


async def edge_voice(text, voice, rate, out):
    import edge_tts
    for attempt in range(5):
        try:
            await edge_tts.Communicate(text, voice, rate=rate).save(str(out))
            if out.exists() and out.stat().st_size > 1000:
                return
        except Exception as e:
            log(f"edge-tts hatasi ({attempt + 1}/5): {e}")
        await asyncio.sleep(5 * (attempt + 1))
    raise RuntimeError("Seslendirme 5 denemede basarisiz oldu.")


async def make_voice(text, spec, base):
    """Ses dosyasinin yolunu dondurur."""
    if OFFLINE:
        out = base.with_suffix(".mp3")
        secs = max(2.0, len(text.split()) * 0.4)
        run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency=220:duration={secs}",
             "-q:a", "4", out])
        return out
    if spec.get("voice_engine", "kokoro") == "kokoro":
        out = base.with_suffix(".wav")
        try:
            kokoro_voice(text, spec.get("voice", "af_heart"), float(spec.get("speed", 0.95)), out)
            return out
        except Exception as e:
            log(f"UYARI: Kokoro calismadi, edge-tts'e geciliyor: {e}")
    out = base.with_suffix(".mp3")
    await edge_voice(text, spec.get("edge_voice", "en-US-AndrewMultilingualNeural"),
                     spec.get("rate", "-5%"), out)
    return out


# ---------- 2) AI GORSEL ----------
def _download(url, headers, tries, out, wait_base):
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=180) as r:
                data = r.read()
                ctype = r.headers.get("Content-Type", "")
            if ctype.startswith("image") and len(data) > 20000:
                out.write_bytes(data)
                return True
            log(f"Beklenmeyen gorsel yaniti: {ctype}, {len(data)} bayt")
        except Exception as e:
            log(f"Gorsel hatasi ({attempt + 1}/{tries}): {e}")
        time.sleep(wait_base * (attempt + 1))
    return False


_ANON_LAST = [0.0]


def fetch_image(prompt, w, h, seed, out, token):
    if OFFLINE:
        return False
    q = urllib.parse.quote(prompt, safe="")
    params = f"width={w}&height={h}&seed={seed}&model=flux&nologo=true"
    ua = {"User-Agent": "lost-worlds-factory/2.0"}
    if token:  # kayitli hesap: filigransiz
        url = f"https://gen.pollinations.ai/image/{q}?{params}"
        if _download(url, {**ua, "Authorization": f"Bearer {token}"}, 3, out, 10):
            return True
        log("UYARI: Anahtarli istek basarisiz, anonim moda geciliyor (filigran olabilir).")
    wait = 16 - (time.time() - _ANON_LAST[0])
    if _ANON_LAST[0] and wait > 0:
        time.sleep(wait)  # anonim limit: ~15 sn'de 1 gorsel
    _ANON_LAST[0] = time.time()
    url = f"https://image.pollinations.ai/prompt/{q}?{params}"
    return _download(url, ua, 5, out, 20)


def placeholder_image(w, h, out):
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=0x2a2018:s={w}x{h}",
         "-frames:v", "1", out])


# ---------- 3) HAREKETLI SAHNE (Ken Burns) ----------
def make_clip(img, audio, dur, w, h, idx, out):
    F = max(1, int(round(dur * FPS)))
    moves = [
        (f"1+0.16*on/{F}", "(iw-iw/zoom)/2", "(ih-ih/zoom)/2"),        # yakinlas
        (f"1.16-0.16*on/{F}", "(iw-iw/zoom)/2", "(ih-ih/zoom)/2"),     # uzaklas
        ("1.14", f"(iw-iw/zoom)*on/{F}", "(ih-ih/zoom)/2"),            # saga kay
        ("1.14", "(iw-iw/zoom)/2", f"(ih-ih/zoom)*(1-on/{F})"),        # yukari kay
        ("1.14", f"(iw-iw/zoom)*(1-on/{F})", "(ih-ih/zoom)/2"),        # sola kay
    ]
    z, x, y = moves[idx % len(moves)]
    vf = (f"[0:v]scale={w * 2}:{h * 2}:force_original_aspect_ratio=increase,"
          f"crop={w * 2}:{h * 2},"
          f"eq=contrast=1.07:saturation=0.92:gamma=0.97,unsharp=5:5:0.6,"
          f"zoompan=z='{z}':x='{x}':y='{y}':d={F}:s={w}x{h}:fps={FPS},"
          f"vignette=PI/5,noise=alls=7:allf=t+u,"
          f"format=yuv420p[v];"
          f"[1:a]apad=pad_dur={PAD},aresample=44100[a]")
    run(["ffmpeg", "-y", "-i", img, "-i", audio, "-filter_complex", vf,
         "-map", "[v]", "-map", "[a]", "-t", f"{dur:.3f}",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", FPS,
         "-c:a", "aac", "-b:a", "192k", "-ac", "2", out])


# ---------- 4) ALTYAZI ----------
def ass_time(t):
    cs = int(round(max(0, t) * 100))
    return f"{cs // 360000}:{(cs // 6000) % 60:02d}:{(cs // 100) % 60:02d}.{cs % 100:02d}"


def clean(s):
    return s.replace("{", "(").replace("}", ")").replace("\n", " ")


def subtitle_events(text, start, audio_dur, words_per_chunk=3):
    words = text.split()
    chunks, cur = [], []
    for wd in words:
        cur.append(wd)
        if len(cur) >= words_per_chunk or wd[-1] in ".,!?;:":
            chunks.append(" ".join(cur))
            cur = []
    if cur:
        chunks.append(" ".join(cur))
    total = sum(len(c) + 1 for c in chunks) or 1
    events, t = [], start
    for c in chunks:
        d = audio_dur * (len(c) + 1) / total
        events.append((t, t + d, "Sub", c.upper()))
        t += d
    return events


def write_ass(path, events, w, h, fmt):
    if fmt == "short":
        fs, mv, hfs, hmv, outline = 80, 560, 64, 250, 5
    else:
        fs, mv, hfs, hmv, outline = 58, 90, 60, 80, 4
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {w}", f"PlayResY: {h}",
        "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Sub,DejaVu Sans,{fs},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,"
        f"-1,0,0,0,100,100,0,0,1,{outline},2,2,70,70,{mv},1",
        f"Style: Hook,DejaVu Sans,{hfs},&H0000D7FF,&H000000FF,&H00000000,&H80000000,"
        f"-1,0,0,0,100,100,0,0,1,{outline},2,8,70,70,{hmv},1",
        "", "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for s, e, style, txt in events:
        lines.append(f"Dialogue: 0,{ass_time(s)},{ass_time(e)},{style},,0,0,0,,{clean(txt)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------- ANA AKIS ----------
async def main():
    if len(sys.argv) < 2:
        sys.exit("Kullanim: python factory.py <video>.json")
    spec_path = Path(sys.argv[1])
    spec = json.loads(spec_path.read_text(encoding="utf-8"))

    fmt = spec.get("format", "short")
    w, h = FORMATS[fmt]
    slug = spec_path.stem
    work = Path("work") / slug
    work.mkdir(parents=True, exist_ok=True)
    outdir = Path("output")
    outdir.mkdir(exist_ok=True)

    style = spec.get("image_style", "")
    seed = int(spec.get("seed", 1000))
    token = os.environ.get("POLLINATIONS_TOKEN", "").strip()
    scenes = spec["scenes"]

    events, clips, t = [], [], 0.0
    first_scene_end = 0.0

    for i, sc in enumerate(scenes):
        log(f"\n=== Sahne {i + 1}/{len(scenes)} ===")
        img = work / f"i{i:03d}.jpg"
        clip = work / f"c{i:03d}.mp4"

        audio = await make_voice(sc["text"], spec, work / f"a{i:03d}")
        ad = media_duration(audio)

        prompt = f"{sc['image']}, {style}" if style else sc["image"]
        if not fetch_image(prompt, w, h, seed + i, img, token):
            log("UYARI: gorsel alinamadi, duz arka plan kullaniliyor.")
            placeholder_image(w, h, img)

        dur = ad + PAD
        make_clip(img, audio, dur, w, h, i, clip)
        clips.append(clip.name)
        events += subtitle_events(sc["text"], t, ad)
        t += dur
        if i == 0:
            first_scene_end = t

    hook = spec.get("hook_text")
    if hook:
        events.insert(0, (0.0, first_scene_end, "Hook", hook))

    (work / "list.txt").write_text("".join(f"file '{c}'\n" for c in clips))
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "list.txt",
         "-c", "copy", "joined.mp4"], cwd=work)
    write_ass(work / "subs.ass", events, w, h, fmt)

    final = (outdir / f"{slug}.mp4").resolve()
    music_files = sorted(Path("music").glob("*.mp3")) if Path("music").exists() else []
    if music_files:
        music = random.Random(seed).choice(music_files).resolve()
        vol = spec.get("music_volume", 0.12)
        log(f"Muzik: {music.name}")
        run(["ffmpeg", "-y", "-i", "joined.mp4", "-stream_loop", "-1", "-i", music,
             "-filter_complex",
             f"[0:v]ass=subs.ass[v];[1:a]volume={vol}[m];"
             f"[0:a][m]amix=inputs=2:duration=first:normalize=0[a]",
             "-map", "[v]", "-map", "[a]",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
             "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", final], cwd=work)
    else:
        run(["ffmpeg", "-y", "-i", "joined.mp4", "-vf", "ass=subs.ass",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
             "-c:a", "copy", "-movflags", "+faststart", final], cwd=work)

    meta = [
        "TITLE:", spec.get("title", ""), "",
        "DESCRIPTION:", spec.get("description", ""), "",
        "TAGS:", ", ".join(spec.get("tags", [])), "",
        "NOT: YouTube'a yuklerken 'Altered or synthetic content' kutusunu isaretle.",
    ]
    (outdir / f"{slug}_metadata.txt").write_text("\n".join(meta), encoding="utf-8")
    log(f"\nBITTI: {final} ({media_duration(final):.1f} sn)")


if __name__ == "__main__":
    asyncio.run(main())
