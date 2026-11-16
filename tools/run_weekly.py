"""Orchestrator — runs the full weekly pipeline end to end.

Usage:
  .venv/Scripts/python tools/run_weekly.py --demo          # offline demo deck, no API keys needed
  .venv/Scripts/python tools/run_weekly.py                 # full run + email
  .venv/Scripts/python tools/run_weekly.py --no-send       # build deck, upload nothing, send nothing
  .venv/Scripts/python tools/run_weekly.py --from classify # resume a failed run from a step (same day)
  .venv/Scripts/python tools/run_weekly.py --date 2026-11-16 --from deck

Steps: discover → videos → classify → metrics → transcripts → insights → deckdata → deck → deliver
On failure: logs the traceback and (unless --no-send) emails an alert instead of a broken deck.
"""
from __future__ import annotations

import subprocess
import sys
import time
import traceback
from datetime import date

import build_deck_data
import classify_videos
import compute_metrics
import deliver
import discover_channels
import fetch_transcripts_comments
import fetch_videos
import llm
import synthesize_insights
from common import ROOT, env, get_logger, run_dir

log = get_logger("run")


def build_deck(run_date):
    d = run_dir(run_date)
    r = subprocess.run(["node", str(ROOT / "tools" / "build_deck.js"), str(d)], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"build_deck.js failed:\n{r.stderr[-2000:]}")
    log.info(r.stdout.strip())


STEPS = [
    ("discover", discover_channels.main),
    ("videos", fetch_videos.main),
    ("classify", classify_videos.main),
    ("metrics", compute_metrics.main),
    ("transcripts", fetch_transcripts_comments.main),
    ("insights", synthesize_insights.main),
    ("deckdata", build_deck_data.main),
    ("deck", build_deck),
]


def run_demo() -> int:
    """Offline demo: sample data -> deck. No API keys, no network, no cost."""
    import runpy
    log.info("━━ demo: generating sample data (no API calls)")
    runpy.run_path(str(ROOT / "tools" / "make_demo_data.py"), run_name="__main__")
    build_deck_data.main("demo")
    build_deck("demo")
    log.info("Demo deck ready: %s", run_dir("demo") / "deck.pptx")
    return 0


def main(argv: list[str]) -> int:
    if "--demo" in argv:
        return run_demo()
    no_send = "--no-send" in argv
    run_date = argv[argv.index("--date") + 1] if "--date" in argv else date.today().isoformat()
    start = argv[argv.index("--from") + 1] if "--from" in argv else STEPS[0][0]
    names = [s[0] for s in STEPS] + ["deliver"]
    if start not in names:
        print(f"--from must be one of {names}")
        return 2

    env("YOUTUBE_API_KEY"); env("ANTHROPIC_API_KEY")
    if not no_send:
        env("REPORT_EMAIL")

    t0 = time.time()
    active = False
    try:
        for name, fn in STEPS:
            active = active or name == start
            if not active:
                continue
            log.info("━━ %s", name)
            res = fn(run_date)
            if res:
                log.info("   %s", res)
        if not no_send:
            log.info("━━ deliver")
            res = deliver.main(run_date)
            log.info("   %s", res)
        else:
            log.info("--no-send: deck at %s", run_dir(run_date) / "deck.pptx")
        log.info("Done in %.1f min. Claude spend this run ~$%.2f", (time.time() - t0) / 60, llm.spent_usd)
        return 0
    except Exception:
        tb = traceback.format_exc()
        log.error("Pipeline failed:\n%s", tb)
        if not no_send:
            try:
                deliver.send_alert(f"Run {run_date} failed.\nResume with: python tools/run_weekly.py --date {run_date} --from <step>\n\n{tb}")
            except Exception as e:
                log.error("Could not send alert email: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
