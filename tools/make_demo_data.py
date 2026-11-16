"""Generate FAKE metrics.json + insights.json in .tmp/run_demo/ so the deck builder can be tested
without API keys. Never used by the real pipeline.

Usage: python tools/make_demo_data.py && python tools/build_deck_data.py --date demo && node tools/build_deck.js .tmp/run_demo
"""
from __future__ import annotations

import random
from datetime import date

from common import run_dir, write_json

random.seed(7)
out = run_dir("demo")
TOPICS = ["n8n Workflows", "Claude Code", "AI Agents", "AI Agency Business", "AI News & Releases", "Vibe Coding",
          "MCP Servers", "Local LLMs", "AI Video Tools", "ChatGPT Tips", "Make.com & Zapier", "Prompt Engineering"]
CH = ["Automation Alley", "Agent Lab", "Prompt Pilot", "The AI Operator", "Build With Bots", "Neural Notes",
      "Workflow Wizard", "LLM Daily", "No-Code Nerd", "Future Stack"]
HOOKS = ["How-to / Tutorial", "Build-along", "Money / Business outcome", "News / Announcement", "Listicle",
         "Bold claim / Hype", "Comparison / Review", "Warning / Mistakes"]


def vid(i, short=False):
    views = int(random.lognormvariate(10.5, 1.1))
    return {"video_id": f"demo{i}", "title": random.choice([
        "I Built an AI Agent That Runs My Entire Business (n8n)", "Claude Code Just Changed Everything",
        "7 AI Automations You Can Sell for $2,000/Month", "Stop Using ChatGPT Like This", "MCP Servers Explained in 12 Minutes",
        "This Free Local LLM Beats GPT (Full Setup)", "How I'd Start an AI Agency in 2026", "Vibe Coding a SaaS in One Afternoon"]),
        "channel": random.choice(CH), "url": "https://www.youtube.com", "thumbnail": None, "thumb_path": None,
        "views": views, "views_per_day": views // 4, "outlier": round(random.uniform(1.2, 9.5), 1), "engagement": 0.041,
        "topic": random.choice(TOPICS), "hook_type": random.choice(HOOKS), "is_short": short, "duration_min": 0.8 if short else 18.0,
        "published_at": "2026-11-12T15:00:00Z", "age_days": 4}


topics = []
for t in TOPICS:
    topics.append({"topic": t, "videos": random.randint(12, 90), "videos_this_week": random.randint(2, 25),
                   "views": random.randint(400_000, 9_000_000), "median_views": random.randint(4000, 60000),
                   "median_outlier": round(random.uniform(0.7, 2.1), 2), "share_this_week": 0.08, "share_prior": 0.08,
                   "momentum": round(random.uniform(-6, 7), 2), "top_video": "I Built an AI Agent That Runs My Entire Business"})
topics.sort(key=lambda t: -t["views"])

m = {
    "is_demo": True,
    "run_date": date.today().isoformat(), "niche": "AI & AI Automation", "timezone": "EST", "window_days": 30, "this_week_days": 7,
    "kpis": {"channels_tracked": 96, "videos_analyzed": 1184, "videos_filtered_off_niche": 141, "uploads_this_week": 287,
             "uploads_prev_week": 262, "views_window": 48_300_000, "views_this_week_uploads": 9_700_000, "median_views_long": 8400,
             "median_engagement": 0.043, "shorts_share_uploads": 0.31, "outliers_3x": 64},
    "top_week": sorted([vid(i, short=(i % 4 == 3)) for i in range(10)], key=lambda v: -v["views"]),
    "outliers": sorted([vid(100 + i) for i in range(12)], key=lambda v: -v["outlier"]),
    "top_shorts": [vid(200 + i, True) for i in range(6)],
    "topics": topics,
    "tools": sorted([{"tool": t, "videos": random.randint(5, 120), "views": random.randint(200_000, 7_000_000),
                      "videos_this_week": random.randint(1, 30), "median_outlier": 1.2}
                     for t in ["n8n", "Claude Code", "ChatGPT", "Claude", "Gemini", "Cursor", "Make.com", "Lovable", "Ollama", "Zapier"]],
                    key=lambda t: -t["views"]),
    "channel_growth_mode": "views_per_subscriber",
    "channels_top_growth": [{"title": c, "thumb_path": None, "subscribers": random.randint(8_000, 400_000), "uploads": random.randint(3, 20),
                             "views_per_sub": round(random.uniform(0.3, 4.0), 2), "sub_delta": None} for c in CH[:8]],
    "channels_top_views": [{"title": c, "thumb_path": None, "views_window": random.randint(500_000, 6_000_000)} for c in CH[:7]],
    "formats": [{"format": "Long-form", "videos": 817, "views": 36_100_000, "median_views": 8400, "median_engagement": 0.046, "median_vpd": 610, "view_share": 0.75},
                {"format": "Shorts", "videos": 367, "views": 12_200_000, "median_views": 5100, "median_engagement": 0.031, "median_vpd": 980, "view_share": 0.25}],
    "hooks": sorted([{"hook_type": h, "videos": random.randint(10, 120), "median_outlier": round(random.uniform(0.7, 1.9), 2), "median_views": 9000} for h in HOOKS],
                    key=lambda h: -h["median_outlier"]),
    "title_features": [{"feature": "Money / $", "with": 1.62, "without": 1.04, "lift": 0.56, "n_with": 88},
                       {"feature": "'I' / personal", "with": 1.41, "without": 0.98, "lift": 0.44, "n_with": 240},
                       {"feature": "Number in title", "with": 1.22, "without": 1.01, "lift": 0.21, "n_with": 310},
                       {"feature": "Brackets ( ) [ ]", "with": 1.0, "without": 1.08, "lift": -0.07, "n_with": 190},
                       {"feature": "Question", "with": 0.86, "without": 1.07, "lift": -0.2, "n_with": 61},
                       {"feature": "ALL-CAPS word", "with": 0.8, "without": 1.09, "lift": -0.27, "n_with": 77}],
    "durations": [{"bucket": b, "videos": random.randint(40, 260), "median_outlier": round(random.uniform(0.8, 1.6), 2), "median_views": 8000}
                  for b in ["<8 min", "8-15 min", "15-25 min", "25-40 min", "40+ min"]],
    "heatmap": {"days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], "blocks": ["00-04", "04-08", "08-12", "12-16", "16-20", "20-24"],
                "cells": [[{"n": 5, "median_outlier": (None if random.random() < 0.2 else round(random.uniform(0.6, 2.4), 2))} for _ in range(6)] for _ in range(7)]},
    "uploads_by_day": [180, 190, 175, 182, 160, 140, 157],
}
ins = {
    "deck_headline": "Claude Code tutorials are eating the niche",
    "niche_mood": "Builders are excited but tired of hype: practical, money-linked automation content outperforms news recaps. Agent tutorials keep growing while generic ChatGPT tips cool off.",
    "exec_summary": [
        {"headline": "Claude Code is the breakout topic", "detail": "Up +6.4pt share of daily views this week; 14 of the top 30 outliers mention it."},
        {"headline": "Money angles beat feature tours", "detail": "Titles with a $ figure average 1.62x their channel norm vs 1.04x without."},
        {"headline": "Long-form still owns attention", "detail": "75% of views go to long-form even though Shorts are 31% of uploads."},
        {"headline": "Viewers want end-to-end builds", "detail": "The most-liked comments ask for full deployment walkthroughs, not just demos."},
    ],
    "slide_notes": [
        {"key": "top_week", "title": "Builds and business outcomes topped the week", "so_what": "Package your next tutorial around a concrete outcome (time saved, $ earned) rather than the tool name."},
        {"key": "outliers", "title": "Small channels broke out with agent builds", "so_what": "Outliers came from sub-50K channels — the topic is pulling, not the creator's audience size."},
        {"key": "topics", "title": "n8n and Claude Code lead total views", "so_what": "Anchor two videos a week in the top-3 topics; use the rest to test emerging ones."},
        {"key": "momentum", "title": "Claude Code and MCP are rising fast", "so_what": "Move now on MCP explainers — attention is rising while few creators cover it well."},
        {"key": "channels", "title": "Mid-size channels are punching above weight", "so_what": "Study the two fastest movers' packaging; both lead with a personal build story."},
        {"key": "formats", "title": "Long-form earns 3x the views of Shorts", "so_what": "Use Shorts as trailers for long-form builds, not as standalone content."},
        {"key": "hooks", "title": "Business outcomes beat news hooks", "so_what": "Lead titles with the result and a number; avoid question-style titles."},
        {"key": "timing", "title": "15-25 minute builds perform best", "so_what": "Target 15-25 minutes and publish Tuesday or Thursday mornings."},
        {"key": "tools", "title": "n8n and Claude dominate tool coverage", "so_what": "Pair a rising tool (Claude Code) with an established one (n8n) to borrow search demand."},
        {"key": "audience", "title": "Viewers want production-ready builds", "so_what": "Close every tutorial with deployment, cost and error-handling — that's the gap viewers name most."},
    ],
    "hook_lessons": [
        {"pattern": "Outcome + number", "example_title": "7 AI Automations You Can Sell for $2,000/Month", "why_it_works": "Promises a concrete, monetisable result and sets an expectation of a checklist."},
        {"pattern": "Personal build story", "example_title": "I Built an AI Agent That Runs My Entire Business", "why_it_works": "First-person proof lowers scepticism and invites viewers to copy the system."},
        {"pattern": "Paradigm shift", "example_title": "Claude Code Just Changed Everything", "why_it_works": "Rides release FOMO; works only when paired with a hands-on demo in the first minute."},
        {"pattern": "Correction / mistake", "example_title": "Stop Using ChatGPT Like This", "why_it_works": "Triggers loss aversion and positions the creator as the expert who knows better."},
    ],
    "audience": {"positive_pct": 58, "neutral_pct": 27, "negative_pct": 15,
                 "mood_summary": "Optimistic and eager to build, but wary of hype and of tutorials that skip the hard production parts.",
                 "top_questions": ["How do I host this so it runs 24/7?", "What does this cost per month at scale?", "Can this work without coding experience?",
                                   "How do I find my first automation client?", "Is n8n or Make better for beginners?"],
                 "pain_points": ["Tutorials stop before deployment", "API costs are unclear", "Too many tools, no clear stack", "Agents break on edge cases"],
                 "requests": ["Full client project start to finish", "Error handling and monitoring", "Cost breakdowns per workflow", "Claude Code for non-devs"]},
    "video_ideas": [
        {"title": "I Built a Claude Code Agent That Replaced My VA", "format": "Long-form", "topic": "Claude Code", "angle": "End-to-end build with costs and deployment shown.", "why_now": "Claude Code +6.4pt momentum; personal-build titles average 1.41x."},
        {"title": "MCP Servers: The Only Guide You Need (2026)", "format": "Long-form", "topic": "MCP Servers", "angle": "Explain, then build 3 useful servers live.", "why_now": "MCP rising +4.1pt while only 23 videos cover it."},
        {"title": "n8n vs Make in 60 seconds", "format": "Short", "topic": "Make.com & Zapier", "angle": "Fast verdict for beginners, link to long-form.", "why_now": "Top-5 recurring question in comments this week."},
        {"title": "5 Automations I'd Sell for $1,500 Each", "format": "Long-form", "topic": "AI Agency Business", "angle": "Show demand, pricing and the build for each.", "why_now": "Money/$ titles show the biggest lift at +56%."},
        {"title": "Why Your AI Agent Breaks (and How to Fix It)", "format": "Long-form", "topic": "AI Agents", "angle": "Error handling, retries and monitoring patterns.", "why_now": "'Agents break' is a top pain point in comments."},
        {"title": "What This Automation Really Costs per Month", "format": "Short", "topic": "n8n Workflows", "angle": "Itemised cost breakdown of a real workflow.", "why_now": "Cost questions appear on 6 of the 10 top videos."},
        {"title": "Deploy n8n 24/7 for $5 — Full Setup", "format": "Long-form", "topic": "n8n Workflows", "angle": "Hosting walkthrough start to finish.", "why_now": "Most-asked question: how to keep workflows running."},
        {"title": "Claude Code for People Who Can't Code", "format": "Long-form", "topic": "Claude Code", "angle": "Beginner build of a useful internal tool.", "why_now": "Explicit viewer request; topic momentum is the week's highest."},
    ],
    "watch_list": ["Whether Claude Code momentum holds once the release buzz fades", "MCP coverage from bigger channels — the window is closing",
                   "Shorts engagement on tool comparisons vs tutorials"],
    "sampled_comments": 1150, "sampled_transcripts": 15,
}
write_json(out / "metrics.json", m)
write_json(out / "insights.json", ins)
print("Demo data written to", out)
