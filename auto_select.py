#!/usr/bin/env python3
import datetime as dt
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

TOPIC_NAMES = [
    "heracleion",
    "cahokia",
    "great-zimbabwe",
    "nan-madol",
    "skara-brae",
    "derinkuyu",
    "akrotiri",
    "catalhoyuk",
    "hattusa",
    "angkor",
    "leptis-magna",
    "mohenjo-daro",
]

def catalog():
    files = []

    for name in TOPIC_NAMES:
        path = ROOT / f"{name}.json"
        if path.exists():
            files.append(path)

    if not files:
        raise SystemExit("No V3 topic JSON files found in repository root.")

    return files


def validate(path):
    data = json.loads(path.read_text(encoding="utf-8"))

    required = ["title", "hook_text", "description", "scenes"]
    missing = [key for key in required if not data.get(key)]

    if missing:
        raise SystemExit(f"{path.name}: missing fields: {missing}")

    if not 6 <= len(data["scenes"]) <= 16:
        raise SystemExit(
            f"{path.name}: number of scenes must be between 6 and 16."
        )

    for index, scene in enumerate(data["scenes"], start=1):
        if not scene.get("text") or not scene.get("image"):
            raise SystemExit(
                f"{path.name}: scene {index} is missing text or image."
            )

    return data


def choose(files, requested):
    if requested and requested != "auto":
        requested = requested.removesuffix(".json")

        for path in files:
            if path.stem == requested:
                return path

        raise SystemExit(f"Unknown V3 topic: {requested}")

    # Aynı UTC günündeki tekrar çalıştırmalar aynı konuyu seçer.
    # Sonraki gün otomatik olarak sıradaki konuya geçer.
    day = dt.datetime.now(dt.timezone.utc).date().toordinal()

    return files[day % len(files)]


def main():
    requested = (
        sys.argv[1]
        if len(sys.argv) > 1
        else os.getenv("VIDEO_TOPIC", "auto")
    )

    files = catalog()
    selected = choose(files, requested)
    data = validate(selected)

    # Workflow bu dosyadan seçilen JSON adını okuyacak.
    Path("selected_topic.txt").write_text(
        selected.stem + "\n",
        encoding="utf-8",
    )

    info = {
        "slug": selected.stem,
        "source": selected.name,
        "title": data["title"],
        "date_utc": str(dt.datetime.now(dt.timezone.utc).date()),
        "catalog_size": len(files),
        "mode": "auto" if requested == "auto" else "manual",
    }

    Path("selection.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(info, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
