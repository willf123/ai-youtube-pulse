"""Step 6 — Claude reads the computed metrics, top-video transcripts and audience comments and writes
the narrative: executive summary, per-slide "so what" notes, hook lessons, audience pulse, video ideas.

Claude never invents numbers here — it is given metrics.json and told to cite only those figures.

Usage: python tools/synthesize_insights.py [--date YYYY-MM-DD]
"""
from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field

import llm
from common import get_logger, load_config, parse_run_date_arg, read_json, run_dir, write_json

log = get_logger("synthesize")

SLIDE_KEYS = Literal["top_week", "outliers", "topics", "momentum", "channels", "formats",
                     "hooks", "timing", "tools", "audience"]


class Takeaway(BaseModel):
    headline: str = Field(description="Max 10 words, punchy, no trailing period")
    detail: str = Field(description="Max 28 words, cites a specific number from the data")


class SlideNote(BaseModel):
    key: SLIDE_KEYS
    title: str = Field(description="Slide title that states the insight, max 8 words, no trailing period")
    so_what: str = Field(description="Max 30 words: what a creator in this niche should do about it")


class HookLesson(BaseModel):
    pattern: str = Field(description="Name of the packaging pattern, max 5 words")
    example_title: str = Field(description="A real title from the data that uses it")
    why_it_works: str = Field(description="Max 22 words")


class AudiencePulse(BaseModel):
    positive_pct: int = Field(description="Share of sampled comments that are positive, 0-100")
    neutral_pct: int
    negative_pct: int = Field(description="positive+neutral+negative must equal 100")
    mood_summary: str = Field(description="Max 30 words on how the audience feels about AI right now")
    top_questions: list[str] = Field(description="5 recurring audience questions, phrased as the viewer would ask, max 14 words each")
    pain_points: list[str] = Field(description="4 frustrations/pain points, max 12 words each")
    requests: list[str] = Field(description="4 things viewers explicitly ask creators to cover, max 12 words each")


class VideoIdea(BaseModel):
    title: str = Field(description="A clickable working title in the style that's winning, max 70 chars")
    format: Literal["Long-form", "Short"]
    topic: str
    angle: str = Field(description="Max 20 words: the specific take / what the video delivers")
    why_now: str = Field(description="Max 22 words: the evidence from this week's data (cite numbers or a video)")


class Insights(BaseModel):
    deck_headline: str = Field(description="The single biggest story this week, max 9 words, no trailing period")
    niche_mood: str = Field(description="2 sentences, max 45 words: the overall feel of the AI YouTube space this week")
    exec_summary: list[Takeaway] = Field(description="Exactly 4 takeaways")
    slide_notes: list[SlideNote] = Field(description="One per slide key")
    hook_lessons: list[HookLesson] = Field(description="Exactly 4")
    audience: AudiencePulse
    video_ideas: list[VideoIdea] = Field(description="Exactly 8, mixed formats, ranked best first")
    watch_list: list[str] = Field(description="3 things to watch next week, max 15 words each")


SYSTEM = """You are a sharp YouTube strategist for creators in the AI and AI-automation niche.
You turn weekly market data into decisions a creator can act on this week.
Rules:
- Every number you mention must come from the METRICS JSON. Never invent or estimate figures.
- An "outlier score" of 3.0 means the video got 3x its channel's median views.
- Be specific and concrete (name tools, topics, real video titles). No generic advice like "be consistent".
- Respect the word limits in the schema — this text goes onto slides."""


def slim_metrics(m: dict) -> dict:
    drop = {"thumbnail", "url", "channel_id"}
    def clean(x):
        if isinstance(x, dict):
            return {k: clean(v) for k, v in x.items() if k not in drop}
        if isinstance(x, list):
            return [clean(v) for v in x]
        return x
    return clean(m)


def main(run_date: str | None = None) -> dict:
    cfg = load_config()
    out = run_dir(run_date)
    m = read_json(out / "metrics.json")
    transcripts = read_json(out / "transcripts.json")
    comments = read_json(out / "comments.json")
    videos = {v["video_id"]: v for v in read_json(out / "videos.json")}

    tx_blocks = []
    for vid, t in transcripts.items():
        v = videos.get(vid, {})
        note = f" (opening {len(t['excerpt'].split())} of {t['words_total']} words)" if t["truncated"] else ""
        tx_blocks.append(f"### {v.get('title')} — {v.get('channel_title')} — {v.get('views', 0):,} views{note}\n{t['excerpt']}")

    cm_blocks = []
    for vid, cs in comments.items():
        v = videos.get(vid, {})
        top = sorted(cs, key=lambda c: -c.get("likes", 0))[:20]
        lines = "\n".join(f"- ({c['likes']} likes) {c['text'][:300]}" for c in top)
        cm_blocks.append(f"### Comments on: {v.get('title')}\n{lines}")

    prompt = f"""Weekly market report for the "{m['niche']}" YouTube niche, run date {m['run_date']}.
Window: videos published in the last {m['window_days']} days; "this week" = last {m['this_week_days']} days.
Publish times are in the report reader's local timezone ({m['timezone']}).

<METRICS>
{json.dumps(slim_metrics(m), ensure_ascii=False)}
</METRICS>

<TRANSCRIPTS description="Opening sections of the top-performing videos — study hooks, structure, promises">
{chr(10).join(tx_blocks) or "(none available this week)"}
</TRANSCRIPTS>

<COMMENTS description="Most-liked comments on this week's biggest videos">
{chr(10).join(cm_blocks) or "(none available this week)"}
</COMMENTS>

Write the insights for this week's slide deck. Slide keys and what each slide shows:
top_week = top 10 videos published this week; outliers = videos that beat their channel's norm the most;
topics = views by topic; momentum = topics gaining/losing share of attention this week vs earlier in the window;
channels = fastest-growing / highest-momentum channels; formats = Shorts vs long-form;
hooks = title/packaging patterns vs outlier score; timing = video length + publish day/time;
tools = AI tools & platforms getting the most views; audience = comment sentiment, questions, requests.
If transcripts or comments are missing, base those sections on titles and metrics and say less rather than guess."""

    ins = llm.structured(SYSTEM, prompt, Insights, effort=cfg["claude"]["synthesis_effort"], max_tokens=48000)
    data = ins.model_dump()
    a = data["audience"]
    s = a["positive_pct"] + a["neutral_pct"] + a["negative_pct"]
    if s and s != 100:  # normalise rounding drift
        a["positive_pct"] = round(a["positive_pct"] * 100 / s)
        a["negative_pct"] = round(a["negative_pct"] * 100 / s)
        a["neutral_pct"] = 100 - a["positive_pct"] - a["negative_pct"]
    data["sampled_comments"] = sum(len(c) for c in comments.values())
    data["sampled_transcripts"] = len(transcripts)
    write_json(out / "insights.json", data)
    log.info("Insights written. Headline: %s", data["deck_headline"])
    return {"usd": round(llm.spent_usd, 3)}


if __name__ == "__main__":
    main(parse_run_date_arg())
