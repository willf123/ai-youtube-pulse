"""Step 1 — Build this run's channel universe.

Sources (merged): seed channels from config, channels behind the top search results
for each keyword, and channels tracked in previous runs (history DB).
Output: .tmp/run_<date>/channels.json, search_hits.json; upserts channels + channel_snapshots.

Usage: python tools/discover_channels.py [--date YYYY-MM-DD]
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta

from common import db, get_logger, load_config, parse_run_date_arg, run_dir, utcnow, write_json
from yt_client import QuotaExceeded, YouTube

log = get_logger("discover")


def main(run_date: str | None = None) -> dict:
    cfg = load_config()
    dcfg = cfg["discovery"]
    out = run_dir(run_date)
    today = run_date or date.today().isoformat()
    yt = YouTube()

    # --- seeds
    seed_ids: set[str] = set()
    raw: dict[str, dict] = {}
    seeds = list(cfg.get("seed_channels") or [])
    if cfg.get("my_channel"):
        seeds.append(cfg["my_channel"])
    my_channel_id = None
    for s in seeds:
        s = s.strip()
        if not s:
            continue
        if s.startswith("UC"):
            seed_ids.add(s)
            if s == cfg.get("my_channel"):
                my_channel_id = s
            continue
        ch = yt.channel_by_handle(s)
        if not ch:
            log.warning("Seed handle %s not found — check config/niche.yaml", s)
            continue
        seed_ids.add(ch["id"])
        raw[ch["id"]] = ch
        if s == cfg.get("my_channel"):
            my_channel_id = ch["id"]

    # --- keyword searches
    after = (utcnow() - timedelta(days=dcfg["lookback_days_search"])).strftime("%Y-%m-%dT%H:%M:%SZ")
    hits = []
    hit_count: Counter = Counter()
    kw_by_channel: dict[str, set] = defaultdict(set)
    for kw in cfg.get("search_keywords", []):
        try:
            items = yt.search_videos(kw, after, dcfg["results_per_keyword"])
        except QuotaExceeded as e:
            log.warning("%s — continuing with %d keywords searched", e, len({h['keyword'] for h in hits}))
            break
        for rank, it in enumerate(items, 1):
            cid = it["snippet"]["channelId"]
            hits.append({"keyword": kw, "rank": rank, "video_id": it["id"]["videoId"], "channel_id": cid})
            hit_count[cid] += 1
            kw_by_channel[cid].add(kw)
        log.info("search '%s': %d results", kw, len(items))

    # --- previously tracked channels
    con = db()
    cutoff = (date.fromisoformat(today) - timedelta(days=60)).isoformat()
    known = {r[0] for r in con.execute("SELECT channel_id FROM channels WHERE last_seen >= ?", (cutoff,))}

    candidates = (seed_ids | set(hit_count) | known) - set(raw)
    for ch in yt.channels(candidates):
        raw[ch["id"]] = ch

    channels = []
    for cid, ch in raw.items():
        st = ch.get("statistics", {})
        subs = int(st.get("subscriberCount", 0) or 0)
        is_seed = cid in seed_ids
        if not is_seed and not st.get("hiddenSubscriberCount") and subs < dcfg["min_subscribers"]:
            continue
        sn = ch["snippet"]
        channels.append({
            "channel_id": cid,
            "title": sn.get("title"),
            "handle": sn.get("customUrl"),
            "thumbnail": (sn.get("thumbnails", {}).get("medium") or sn.get("thumbnails", {}).get("default") or {}).get("url"),
            "subscribers": subs,
            "total_views": int(st.get("viewCount", 0) or 0),
            "video_count": int(st.get("videoCount", 0) or 0),
            "uploads_playlist": ch.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads"),
            "is_seed": is_seed,
            "is_mine": cid == my_channel_id,
            "search_hits": hit_count.get(cid, 0),
            "keywords": sorted(kw_by_channel.get(cid, [])),
            "source": "seed" if is_seed else ("search" if cid in hit_count else "history"),
        })

    # cap: seeds always, then by search hits, then subscribers
    seeds_list = [c for c in channels if c["is_seed"]]
    rest = sorted((c for c in channels if not c["is_seed"]), key=lambda c: (-c["search_hits"], -c["subscribers"]))
    channels = seeds_list + rest[: max(0, dcfg["max_channels"] - len(seeds_list))]

    # --- persist
    for c in channels:
        con.execute(
            """INSERT INTO channels(channel_id,title,handle,thumbnail,uploads_playlist,source,first_seen,last_seen)
               VALUES(?,?,?,?,?,?,?,?)
               ON CONFLICT(channel_id) DO UPDATE SET title=excluded.title, handle=excluded.handle,
                 thumbnail=excluded.thumbnail, uploads_playlist=excluded.uploads_playlist, last_seen=excluded.last_seen""",
            (c["channel_id"], c["title"], c["handle"], c["thumbnail"], c["uploads_playlist"], c["source"], today, today),
        )
        con.execute(
            "INSERT OR REPLACE INTO channel_snapshots VALUES(?,?,?,?,?)",
            (c["channel_id"], today, c["subscribers"], c["total_views"], c["video_count"]),
        )
    con.execute("INSERT INTO quota_log VALUES(?,?,?)", (today, "discover", yt.units))
    con.commit()
    con.close()

    write_json(out / "channels.json", channels)
    write_json(out / "search_hits.json", hits)
    log.info("Tracking %d channels (%d seeds). Quota used: %d units", len(channels), len(seeds_list), yt.units)
    return {"channels": len(channels), "units": yt.units}


if __name__ == "__main__":
    main(parse_run_date_arg())
