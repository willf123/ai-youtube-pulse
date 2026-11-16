"""Step 7 — Merge metrics.json + insights.json into deck_data.json and download thumbnails/avatars
so the Node deck builder works fully offline.

Usage: python tools/build_deck_data.py [--date YYYY-MM-DD]
"""
from __future__ import annotations

import hashlib

import requests

from common import get_logger, load_config, parse_run_date_arg, read_json, run_dir, write_json

log = get_logger("deckdata")


def fetch_image(url: str | None, folder) -> str | None:
    if not url:
        return None
    folder.mkdir(exist_ok=True)
    path = folder / (hashlib.md5(url.encode()).hexdigest()[:16] + ".jpg")
    if path.exists():
        return str(path)
    try:
        r = requests.get(url, timeout=20)
        if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
            path.write_bytes(r.content)
            return str(path)
    except requests.RequestException:
        pass
    return None


def main(run_date: str | None = None) -> dict:
    cfg = load_config()
    out = run_dir(run_date)
    m = read_json(out / "metrics.json")
    ins = read_json(out / "insights.json")
    thumbs = out / "thumbs"

    for key in ("top_week", "outliers", "top_shorts"):
        for v in m.get(key, []):
            v["thumb_path"] = fetch_image(v.get("thumbnail"), thumbs)
    for key in ("channels_top_growth", "channels_top_views"):
        for c in m.get(key, []):
            c["thumb_path"] = fetch_image(c.get("thumbnail"), thumbs)

    deck = {"metrics": m, "insights": ins, "subject_prefix": cfg["delivery"]["subject_prefix"]}
    write_json(out / "deck_data.json", deck)
    log.info("deck_data.json ready (%d images)", len(list(thumbs.glob("*.jpg"))) if thumbs.exists() else 0)
    return {"ok": True}


if __name__ == "__main__":
    main(parse_run_date_arg())
