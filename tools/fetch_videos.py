"""Step 2 — Pull every upload in the analysis window for each tracked channel, with stats.

Reads channels.json + search_hits.json, writes videos.json (+ refreshed channels.json),
and stores a per-video snapshot in the history DB (for week-over-week deltas).
Off-niche channels (share of in-niche uploads < min_niche_share) are dropped unless seeded.

Usage: python tools/fetch_videos.py [--date YYYY-MM-DD]
"""
from __future__ import annotations

import re
from datetime import date, timedelta

import isodate

from common import db, get_logger, load_config, parse_run_date_arg, read_json, run_dir, utcnow, write_json
from yt_client import YouTube

log = get_logger("videos")


def niche_matcher(terms: list[str]):
    # word-boundary match so "ai" doesn't hit "said"/"email"
    pats = [re.compile(r"(?<![a-z0-9])" + re.escape(t.lower()) + r"(?![a-z0-9])") for t in terms]
    return lambda text: any(p.search(text) for p in pats)


def main(run_date: str | None = None) -> dict:
    cfg = load_config()
    acfg, dcfg = cfg["analysis"], cfg["discovery"]
    out = run_dir(run_date)
    today = run_date or date.today().isoformat()
    channels = read_json(out / "channels.json")
    hits = read_json(out / "search_hits.json")
    yt = YouTube()

    window_start = (utcnow() - timedelta(days=acfg["window_days"])).strftime("%Y-%m-%dT%H:%M:%SZ")
    ids: set[str] = set()
    for c in channels:
        if not c.get("uploads_playlist"):
            continue
        for it in yt.playlist_items(c["uploads_playlist"], window_start):
            ids.add(it["contentDetails"]["videoId"])
    tracked = {c["channel_id"] for c in channels}
    ids |= {h["video_id"] for h in hits if h["channel_id"] in tracked}
    log.info("Fetching stats for %d videos from %d channels", len(ids), len(channels))

    in_niche = niche_matcher(cfg["niche_terms"])
    hit_kw: dict[str, list] = {}
    for h in hits:
        hit_kw.setdefault(h["video_id"], []).append(h["keyword"])

    videos = []
    for v in yt.videos(ids):
        sn, cd, st = v["snippet"], v.get("contentDetails", {}), v.get("statistics", {})
        if sn.get("liveBroadcastContent") in ("live", "upcoming"):
            continue
        if sn["publishedAt"] < window_start:
            continue
        try:
            dur = int(isodate.parse_duration(cd.get("duration", "PT0S")).total_seconds())
        except Exception:
            dur = 0
        title = sn.get("title", "")
        desc = sn.get("description", "") or ""
        tags = sn.get("tags", []) or []
        text = " ".join([title, " ".join(tags), desc[:500]]).lower()
        is_short = dur <= 60 or (dur <= acfg["shorts_max_seconds"] and "#short" in text)
        thumbs = sn.get("thumbnails", {})
        thumb = (thumbs.get("maxres") or thumbs.get("high") or thumbs.get("medium") or {}).get("url")
        videos.append({
            "video_id": v["id"],
            "channel_id": sn["channelId"],
            "channel_title": sn.get("channelTitle"),
            "title": title,
            "description": desc[:1000],
            "tags": tags[:20],
            "published_at": sn["publishedAt"],
            "duration_s": dur,
            "is_short": is_short,
            "views": int(st.get("viewCount", 0) or 0),
            "likes": int(st.get("likeCount", 0) or 0),
            "comments": int(st.get("commentCount", 0) or 0),
            "thumbnail": thumb,
            "in_niche": in_niche(text),
            "search_keywords": hit_kw.get(v["id"], []),
            "url": f"https://www.youtube.com/watch?v={v['id']}",
        })

    # drop off-niche channels (seeds exempt)
    by_ch: dict[str, list] = {}
    for v in videos:
        by_ch.setdefault(v["channel_id"], []).append(v)
    keep = set()
    for c in channels:
        vs = by_ch.get(c["channel_id"], [])
        share = (sum(v["in_niche"] for v in vs) / len(vs)) if vs else 0
        c["niche_share"] = round(share, 2)
        c["videos_in_window"] = len(vs)
        if c["is_seed"] or share >= dcfg["min_niche_share"]:
            keep.add(c["channel_id"])
    dropped = [c["title"] for c in channels if c["channel_id"] not in keep]
    if dropped:
        log.info("Dropped %d off-niche channels: %s", len(dropped), ", ".join(dropped[:15]))
    channels = [c for c in channels if c["channel_id"] in keep]
    videos = [v for v in videos if v["channel_id"] in keep]

    con = db()
    con.executemany(
        "INSERT OR REPLACE INTO video_snapshots VALUES(?,?,?,?,?,?,?,?,?,?)",
        [(v["video_id"], today, v["channel_id"], v["title"], v["published_at"], v["duration_s"],
          int(v["is_short"]), v["views"], v["likes"], v["comments"]) for v in videos],
    )
    con.execute("INSERT INTO quota_log VALUES(?,?,?)", (today, "fetch_videos", yt.units))
    con.commit()
    con.close()

    write_json(out / "channels.json", channels)
    write_json(out / "videos.json", videos)
    log.info("Saved %d videos (%d in-niche). Quota used: %d units", len(videos), sum(v["in_niche"] for v in videos), yt.units)
    return {"videos": len(videos), "units": yt.units}


if __name__ == "__main__":
    main(parse_run_date_arg())
