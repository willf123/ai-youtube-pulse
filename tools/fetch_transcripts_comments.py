"""Step 5 — Transcripts (free, youtube-transcript-api) + top comments (YouTube API, 1 unit/video)
for the videos chosen in selection.json.

Transcript fetching is unofficial scraping: YouTube may throttle/block an IP after many requests.
We pace requests and simply skip failures — the report degrades gracefully without them.

Usage: python tools/fetch_transcripts_comments.py [--date YYYY-MM-DD]
"""
from __future__ import annotations

import time
from datetime import date

from youtube_transcript_api import YouTubeTranscriptApi

from common import db, get_logger, load_config, parse_run_date_arg, read_json, run_dir, write_json
from yt_client import QuotaExceeded, YouTube

log = get_logger("transcripts")


def main(run_date: str | None = None) -> dict:
    cfg = load_config()
    acfg = cfg["analysis"]
    out = run_dir(run_date)
    today = run_date or date.today().isoformat()
    sel = read_json(out / "selection.json")

    api = YouTubeTranscriptApi()
    transcripts = {}
    for vid in sel["transcripts"]:
        try:
            fetched = api.fetch(vid, languages=["en", "en-US", "en-GB"])
            words = " ".join(s.text for s in fetched).replace("\n", " ").split()
            transcripts[vid] = {
                "words_total": len(words),
                "excerpt": " ".join(words[: acfg["transcript_word_limit"]]),
                "truncated": len(words) > acfg["transcript_word_limit"],
            }
        except Exception as e:  # disabled captions, IP block, age-restricted…
            log.warning("No transcript for %s: %s", vid, type(e).__name__)
        time.sleep(1.5)
    log.info("Transcripts: %d/%d", len(transcripts), len(sel["transcripts"]))

    yt = YouTube()
    comments = {}
    try:
        for vid in sel["comments"]:
            c = yt.top_comments(vid, acfg["comments_per_video"])
            if c:
                comments[vid] = c
    except QuotaExceeded as e:
        log.warning("%s — continuing with %d videos' comments", e, len(comments))
    log.info("Comments: %d videos, %d comments", len(comments), sum(len(v) for v in comments.values()))

    con = db()
    con.execute("INSERT INTO quota_log VALUES(?,?,?)", (today, "comments", yt.units))
    con.commit()
    con.close()
    write_json(out / "transcripts.json", transcripts)
    write_json(out / "comments.json", comments)
    return {"transcripts": len(transcripts), "comment_videos": len(comments)}


if __name__ == "__main__":
    main(parse_run_date_arg())
