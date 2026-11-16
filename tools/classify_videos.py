"""Step 3 — Claude tags every video: topic (from a stable weekly taxonomy), hook type, tools mentioned,
and a niche-relevance verdict. Deterministic code does all the counting afterwards.

Reads videos.json, writes video_tags.json + taxonomy.json; stores taxonomy in history DB so topic
names stay stable week to week.

Usage: python tools/classify_videos.py [--date YYYY-MM-DD]
"""
from __future__ import annotations

import json
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

import llm
from common import db, get_logger, load_config, parse_run_date_arg, read_json, run_dir, write_json

log = get_logger("classify")

HOOK_TYPES = Literal[
    "How-to / Tutorial", "Build-along", "News / Announcement", "Listicle", "Bold claim / Hype",
    "Money / Business outcome", "Comparison / Review", "Question / Curiosity", "Story / Case study",
    "Warning / Mistakes", "Opinion / Commentary", "Other",
]


class Topic(BaseModel):
    name: str = Field(description="Short topic label, 1-4 words, e.g. 'n8n Workflows', 'Claude Code', 'AI Agency Business'")
    description: str = Field(description="One sentence on what belongs in this topic")


class Taxonomy(BaseModel):
    topics: list[Topic]


class VideoTag(BaseModel):
    video_id: str
    topic: str = Field(description="Exactly one topic name from the taxonomy, or 'Other'")
    hook_type: HOOK_TYPES
    tools: list[str] = Field(description="Canonical product/tool/model names the video is about (e.g. 'n8n', 'Claude', 'ChatGPT', 'Cursor'). Empty if none.")
    is_niche: bool = Field(description="True if the video is genuinely about AI or AI automation")


class TagBatch(BaseModel):
    items: list[VideoTag]


SYSTEM = (
    "You are a YouTube market analyst for the AI and AI-automation creator niche. "
    "You label videos consistently so the labels can be aggregated into charts."
)


def build_taxonomy(videos: list[dict], prior: list[dict], effort: str) -> list[dict]:
    titles = "\n".join(f"- {v['title']} ({v['views']:,} views)" for v in sorted(videos, key=lambda v: -v["views"])[:600])
    prior_txt = "\n".join(f"- {t['topic']}: {t['description']}" for t in prior) or "(none — first run)"
    prompt = f"""Below are titles of recent videos from AI / AI-automation YouTube channels.

Design a topic taxonomy of 10-14 topics that covers them, for weekly trend tracking.
- Topics should be about subject matter (what the video is about), not format.
- Make them specific enough to be useful to a creator in this niche (e.g. "n8n Workflows" beats "Automation").
- Last week's taxonomy is below. Reuse those exact names where they still fit, so trends stay comparable;
  add or retire topics only when the content clearly shifted.

Last week's taxonomy:
{prior_txt}

Video titles:
{titles}"""
    tax = llm.structured(SYSTEM, prompt, Taxonomy, effort=effort, max_tokens=8000)
    return [{"topic": t.name, "description": t.description} for t in tax.topics]


def tag_batch(batch: list[dict], taxonomy: list[dict], effort: str) -> list[VideoTag]:
    tax_txt = "\n".join(f"- {t['topic']}: {t['description']}" for t in taxonomy)
    rows = "\n".join(
        json.dumps({"video_id": v["video_id"], "title": v["title"], "channel": v["channel_title"],
                    "tags": v["tags"][:8], "description": v["description"][:200]}, ensure_ascii=False)
        for v in batch
    )
    prompt = f"""Label each video below. Return one item per video_id, in the same order, covering every video.

Topic taxonomy (use these names exactly; 'Other' if nothing fits):
{tax_txt}

hook_type = the main angle of the title/packaging.
tools = canonical names of AI products, models or automation platforms the video centres on
(normalise: 'GPT-5', 'ChatGPT' -> 'ChatGPT'; 'Claude Code' stays 'Claude Code'; 'make' -> 'Make.com').

Videos (JSON lines):
{rows}"""
    return llm.structured(SYSTEM, prompt, TagBatch, effort=effort, max_tokens=32000).items


def main(run_date: str | None = None) -> dict:
    cfg = load_config()
    effort = cfg["claude"]["classify_effort"]
    out = run_dir(run_date)
    today = run_date or date.today().isoformat()
    videos = read_json(out / "videos.json")

    con = db()
    last = con.execute("SELECT MAX(snapshot_date) FROM topic_taxonomy WHERE snapshot_date < ?", (today,)).fetchone()[0]
    prior = [{"topic": r[0], "description": r[1]} for r in
             con.execute("SELECT topic, description FROM topic_taxonomy WHERE snapshot_date = ?", (last,))] if last else []

    niche_videos = [v for v in videos if v["in_niche"]] or videos
    taxonomy = build_taxonomy(niche_videos, prior, effort)
    log.info("Taxonomy: %s", ", ".join(t["topic"] for t in taxonomy))

    valid_topics = {t["topic"] for t in taxonomy} | {"Other"}
    tags: dict[str, dict] = {}
    BATCH = 120
    for i in range(0, len(videos), BATCH):
        batch = videos[i:i + BATCH]
        for t in tag_batch(batch, taxonomy, effort):
            d = t.model_dump()
            if d["topic"] not in valid_topics:
                d["topic"] = "Other"
            tags[d["video_id"]] = d
        log.info("Tagged %d/%d", min(i + BATCH, len(videos)), len(videos))

    missing = [v["video_id"] for v in videos if v["video_id"] not in tags]
    if missing:
        log.warning("%d videos came back untagged; marking as Other", len(missing))
        for vid in missing:
            tags[vid] = {"video_id": vid, "topic": "Other", "hook_type": "Other", "tools": [], "is_niche": True}

    con.execute("DELETE FROM topic_taxonomy WHERE snapshot_date = ?", (today,))
    con.executemany("INSERT INTO topic_taxonomy VALUES(?,?,?)", [(today, t["topic"], t["description"]) for t in taxonomy])
    con.commit()
    con.close()

    write_json(out / "taxonomy.json", taxonomy)
    write_json(out / "video_tags.json", list(tags.values()))
    return {"tagged": len(tags), "usd": round(llm.spent_usd, 3)}


if __name__ == "__main__":
    main(parse_run_date_arg())
