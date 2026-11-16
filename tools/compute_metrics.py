"""Step 4 — Deterministic metrics (pandas). No LLM here: every number in the deck comes from this file.

Key metrics
- views_per_day   = views / age in days
- outlier score   = video views / median views of that channel's same-format videos in the window
                    (>= 3 comparable videos required). 3x = the video did 3x the channel's norm.
- engagement      = (likes + comments) / views
- topic momentum  = topic's share of views-per-day among videos published this week
                    vs its share among videos published earlier in the window

Reads videos.json, video_tags.json, channels.json (+ history DB for week-over-week growth).
Writes metrics.json and selection.json (which videos get transcripts/comments).

Usage: python tools/compute_metrics.py [--date YYYY-MM-DD]
"""
from __future__ import annotations

import re
from datetime import date, timedelta

import numpy as np
import pandas as pd

from common import as_date, db, get_logger, load_config, parse_run_date_arg, read_json, run_dir, utcnow, write_json

log = get_logger("metrics")
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
HOUR_BLOCKS = ["00-04", "04-08", "08-12", "12-16", "16-20", "20-24"]


def _f(x, nd=2):
    """JSON-safe float."""
    if x is None or (isinstance(x, float) and (np.isnan(x) or np.isinf(x))):
        return None
    return round(float(x), nd)


def video_card(r) -> dict:
    return {
        "video_id": r.video_id, "title": r.title, "channel": r.channel_title, "url": r.url,
        "thumbnail": r.thumbnail, "views": int(r.views), "views_per_day": _f(r.vpd, 0),
        "outlier": _f(r.outlier, 1), "engagement": _f(r.engagement, 4), "topic": r.topic,
        "hook_type": r.hook_type, "is_short": bool(r.is_short), "duration_min": _f(r.duration_s / 60, 1),
        "published_at": r.published_at, "age_days": _f(r.age_days, 1),
    }


def title_features(t: str) -> dict:
    return {
        "Number in title": bool(re.search(r"\d", t)),
        "Question": "?" in t,
        "Money / $": bool(re.search(r"\$|\bmoney\b|\bincome\b|\bprofit\b|\brevenue\b|\b\d+k\b", t, re.I)),
        "ALL-CAPS word": bool(re.search(r"\b[A-Z]{3,}\b", re.sub(r"\b(AI|GPT|LLM|MCP|API|SEO|RAG|AGI|CEO|USA)\b", "", t))),
        "Brackets ( ) [ ]": bool(re.search(r"[\(\[]", t)),
        "Under 50 chars": len(t) < 50,
        "'I' / personal": bool(re.search(r"\b(I|I'm|I've|my|me)\b", t)),
        "New / just released": bool(re.search(r"\bnew\b|\bjust\b|\breleased?\b|\blaunch", t, re.I)),
    }


def main(run_date: str | None = None) -> dict:
    cfg = load_config()
    acfg = cfg["analysis"]
    out = run_dir(run_date)
    today = run_date or date.today().isoformat()

    videos = pd.DataFrame(read_json(out / "videos.json"))
    tags = pd.DataFrame(read_json(out / "video_tags.json"))
    channels = pd.DataFrame(read_json(out / "channels.json"))
    df = videos.merge(tags, on="video_id", how="left")
    df["topic"] = df["topic"].fillna("Other")
    df["hook_type"] = df["hook_type"].fillna("Other")
    df["tools"] = df["tools"].apply(lambda x: x if isinstance(x, list) else [])
    df["is_niche"] = df["is_niche"].fillna(df["in_niche"]).astype(bool)

    total_raw = len(df)
    df = df[df["is_niche"]].copy()
    now = utcnow()
    df["published"] = pd.to_datetime(df["published_at"], utc=True)
    df["age_days"] = ((now - df["published"]).dt.total_seconds() / 86400).clip(lower=0.25)
    df["vpd"] = df["views"] / df["age_days"]
    df["engagement"] = np.where(df["views"] > 0, (df["likes"] + df["comments"]) / df["views"], np.nan)

    # channel baseline per format
    grp = df.groupby(["channel_id", "is_short"])["views"]
    df["ch_median"] = grp.transform("median")
    df["ch_n"] = grp.transform("count")
    df["outlier"] = np.where((df["ch_n"] >= 3) & (df["ch_median"] > 0), df["views"] / df["ch_median"], np.nan)

    week_cut = now - timedelta(days=acfg["this_week_days"])
    df["this_week"] = df["published"] >= week_cut
    week, prior = df[df["this_week"]], df[~df["this_week"]]
    long_ = df[~df["is_short"]]

    # local timezone for posting-time analysis
    local_tz = now.astimezone().tzinfo
    local = df["published"].dt.tz_convert(local_tz)
    df["dow"] = local.dt.day_of_week
    df["hblock"] = local.dt.hour // 4

    m: dict = {"run_date": as_date(run_date).isoformat(),"niche": cfg["niche_name"], "timezone": str(now.astimezone().tzname()),
               "window_days": acfg["window_days"], "this_week_days": acfg["this_week_days"]}

    # ---- KPIs
    prev_week = df[(df["published"] < week_cut) & (df["published"] >= week_cut - timedelta(days=acfg["this_week_days"]))]
    m["kpis"] = {
        "channels_tracked": int(df["channel_id"].nunique()),
        "videos_analyzed": int(len(df)),
        "videos_filtered_off_niche": int(total_raw - len(df)),
        "uploads_this_week": int(len(week)),
        "uploads_prev_week": int(len(prev_week)),
        "views_window": int(df["views"].sum()),
        "views_this_week_uploads": int(week["views"].sum()),
        "median_views_long": _f(long_["views"].median(), 0),
        "median_engagement": _f(df["engagement"].median(), 4),
        "shorts_share_uploads": _f(df["is_short"].mean(), 3),
        "outliers_3x": int((df["outlier"] >= 3).sum()),
    }

    # ---- top videos this week & outliers
    m["top_week"] = [video_card(r) for r in week.sort_values("views", ascending=False).head(10).itertuples()]
    outl = long_[(long_["outlier"] >= 1.5) & (long_["views"] >= 5000)].sort_values("outlier", ascending=False)
    m["outliers"] = [video_card(r) for r in outl.head(12).itertuples()]
    m["top_shorts"] = [video_card(r) for r in df[df["is_short"]].sort_values("vpd", ascending=False).head(6).itertuples()]

    # ---- topics
    tw_total = week["vpd"].sum() or 1
    tp_total = prior["vpd"].sum() or 1
    topics = []
    for name, g in df.groupby("topic"):
        gw, gp = g[g["this_week"]], g[~g["this_week"]]
        share_w = gw["vpd"].sum() / tw_total
        share_p = gp["vpd"].sum() / tp_total
        topics.append({
            "topic": name, "videos": int(len(g)), "videos_this_week": int(len(gw)),
            "views": int(g["views"].sum()), "median_views": _f(g["views"].median(), 0),
            "median_outlier": _f(g["outlier"].median(), 2),
            "share_this_week": _f(share_w, 4), "share_prior": _f(share_p, 4),
            "momentum": _f((share_w - share_p) * 100, 2),  # percentage-point change in attention share
            "top_video": (g.sort_values("views", ascending=False).iloc[0]["title"]),
        })
    topics.sort(key=lambda t: -t["views"])
    m["topics"] = topics

    # ---- tools / products
    ex = df.explode("tools").dropna(subset=["tools"])
    ex = ex[ex["tools"].astype(str).str.len() > 0]
    tools = []
    for name, g in ex.groupby("tools"):
        tools.append({"tool": name, "videos": int(len(g)), "views": int(g["views"].sum()),
                      "videos_this_week": int(g["this_week"].sum()),
                      "median_outlier": _f(g["outlier"].median(), 2)})
    tools.sort(key=lambda t: -t["views"])
    m["tools"] = tools[:15]

    # ---- channels
    con = db()
    prev_snap = pd.read_sql_query(
        """SELECT s.channel_id, s.subscribers, s.snapshot_date FROM channel_snapshots s
           JOIN (SELECT channel_id, MAX(snapshot_date) d FROM channel_snapshots
                 WHERE snapshot_date <= ? GROUP BY channel_id) x
           ON s.channel_id = x.channel_id AND s.snapshot_date = x.d""",
        con, params=((as_date(run_date) - timedelta(days=5)).isoformat(),))
    con.close()
    ch = channels.set_index("channel_id")
    ch_rows = []
    for cid, g in df.groupby("channel_id"):
        if cid not in ch.index:
            continue
        c = ch.loc[cid]
        subs = int(c["subscribers"] or 0)
        prev = prev_snap[prev_snap["channel_id"] == cid]
        sub_delta = int(subs - prev["subscribers"].iloc[0]) if len(prev) and subs else None
        ch_rows.append({
            "channel_id": cid, "title": c["title"], "thumbnail": c["thumbnail"], "subscribers": subs,
            "uploads": int(len(g)), "uploads_this_week": int(g["this_week"].sum()),
            "views_window": int(g["views"].sum()),
            "views_this_week_uploads": int(g.loc[g["this_week"], "views"].sum()),
            "views_per_sub": _f(g["views"].sum() / subs, 3) if subs else None,
            "sub_delta": sub_delta,
            "sub_delta_pct": _f(sub_delta / prev["subscribers"].iloc[0], 4) if sub_delta is not None and prev["subscribers"].iloc[0] else None,
            "median_outlier": _f(g["outlier"].median(), 2),
            "is_mine": bool(c.get("is_mine", False)),
        })
    has_growth = any(r["sub_delta"] is not None for r in ch_rows)
    m["channel_growth_mode"] = "subscriber_delta" if has_growth else "views_per_subscriber"
    key = (lambda r: -(r["sub_delta"] or 0)) if has_growth else (lambda r: -(r["views_per_sub"] or 0))
    eligible = [r for r in ch_rows if r["subscribers"] >= 1000]
    m["channels_top_growth"] = sorted(eligible, key=key)[:10]
    m["channels_top_views"] = sorted(ch_rows, key=lambda r: -r["views_window"])[:10]
    mine = [r for r in ch_rows if r["is_mine"]]
    m["my_channel"] = mine[0] if mine else None

    # ---- shorts vs long-form
    fmt = []
    for label, g in (("Long-form", df[~df["is_short"]]), ("Shorts", df[df["is_short"]])):
        fmt.append({"format": label, "videos": int(len(g)), "views": int(g["views"].sum()),
                    "median_views": _f(g["views"].median(), 0), "median_engagement": _f(g["engagement"].median(), 4),
                    "median_vpd": _f(g["vpd"].median(), 0)})
    tv = sum(f["views"] for f in fmt) or 1
    for f in fmt:
        f["view_share"] = _f(f["views"] / tv, 3)
    m["formats"] = fmt

    # ---- hooks & title features (long-form, needs an outlier score)
    lo = long_[long_["outlier"].notna()]
    hooks = []
    for name, g in lo.groupby("hook_type"):
        if len(g) >= 3:
            hooks.append({"hook_type": name, "videos": int(len(g)), "median_outlier": _f(g["outlier"].median(), 2),
                          "median_views": _f(g["views"].median(), 0)})
    m["hooks"] = sorted(hooks, key=lambda h: -(h["median_outlier"] or 0))
    feats = pd.DataFrame([title_features(t) for t in lo["title"]], index=lo.index)
    tf = []
    for col in feats.columns:
        w, wo = lo[feats[col]], lo[~feats[col]]
        if len(w) >= 5 and len(wo) >= 5:
            tf.append({"feature": col, "with": _f(w["outlier"].median(), 2), "without": _f(wo["outlier"].median(), 2),
                       "lift": _f(w["outlier"].median() / wo["outlier"].median() - 1, 3), "n_with": int(len(w))})
    m["title_features"] = sorted(tf, key=lambda x: -(x["lift"] or 0))

    # ---- duration buckets (long-form)
    bins = [0, 8, 15, 25, 40, 10_000]
    labels = ["<8 min", "8-15 min", "15-25 min", "25-40 min", "40+ min"]
    lo2 = long_.copy()
    lo2["dur_bucket"] = pd.cut(lo2["duration_s"] / 60, bins=bins, labels=labels, right=False)
    dur = []
    for lab in labels:
        g = lo2[lo2["dur_bucket"] == lab]
        dur.append({"bucket": lab, "videos": int(len(g)), "median_outlier": _f(g["outlier"].median(), 2),
                    "median_views": _f(g["views"].median(), 0)})
    m["durations"] = dur

    # ---- publish-time heatmap (long-form, median outlier, local time)
    heat = []
    for d in range(7):
        row = []
        for h in range(6):
            g = lo2[(df.loc[lo2.index, "dow"] == d) & (df.loc[lo2.index, "hblock"] == h)]
            g = g[g["outlier"].notna()]
            row.append({"n": int(len(g)), "median_outlier": _f(g["outlier"].median(), 2) if len(g) >= 2 else None})
        heat.append(row)
    m["heatmap"] = {"days": DAYS, "blocks": HOUR_BLOCKS, "cells": heat}
    m["uploads_by_day"] = [int((df["dow"] == d).sum()) for d in range(7)]

    # ---- selection for transcripts & comments
    pool = pd.concat([outl.head(acfg["top_n_transcripts"]),
                      week[~week["is_short"]].sort_values("views", ascending=False).head(acfg["top_n_transcripts"])])
    pool = pool.drop_duplicates("video_id")
    transcripts = pool.sort_values("outlier", ascending=False, na_position="last").head(acfg["top_n_transcripts"])["video_id"].tolist()
    cpool = pd.concat([week.sort_values("views", ascending=False), outl]).drop_duplicates("video_id")
    comments = cpool[cpool["comments"] > 0].head(acfg["top_n_comments_videos"])["video_id"].tolist()
    write_json(out / "selection.json", {"transcripts": transcripts, "comments": comments})

    write_json(out / "metrics.json", m)
    log.info("Metrics: %d niche videos, %d topics, %d outliers, growth mode=%s",
             len(df), len(topics), len(m["outliers"]), m["channel_growth_mode"])
    return {"videos": len(df)}


if __name__ == "__main__":
    main(parse_run_date_arg())
