# Workflow: Weekly AI-Niche YouTube Intelligence Deck

## Objective
Every week, analyse what's working across AI / AI-automation YouTube (topics, outlier videos, title hooks,
formats, timing, tools, audience sentiment) and email a designed slide deck (PPTX + PDF + Google Slides link)
with concrete video ideas.

## Inputs
- `config/niche.yaml`: seed channels, search keywords, niche terms, thresholds, Claude model. **Edit this to tune the report.**
- `.env`: `YOUTUBE_API_KEY`, `ANTHROPIC_API_KEY`, `REPORT_EMAIL`
- `credentials.json` / `token.json`: Google OAuth (Drive + Gmail send)

## Run
```
.venv/Scripts/python tools/run_weekly.py              # full run + email
.venv/Scripts/python tools/run_weekly.py --no-send    # build deck only (.tmp/run_<date>/deck.pptx)
.venv/Scripts/python tools/run_weekly.py --from insights   # resume a failed run from a step (same day)
```
Scheduled run: Windows Task Scheduler task **"YouTube Weekly Pulse"**, which runs `run_weekly.bat` (Mondays 07:00).

## Steps (tools/)
| # | Step | Tool | Output (.tmp/run_<date>/) | Cost |
|---|------|------|---------------------------|------|
| 1 | discover | `discover_channels.py` | channels.json, search_hits.json | ~100 units/keyword (20 keywords ≈ 2,000) + ~20 |
| 2 | videos | `fetch_videos.py` | videos.json (+ DB snapshot) | ~1–2 units/channel + 1 per 50 videos |
| 3 | classify | `classify_videos.py` | taxonomy.json, video_tags.json | Claude: topic/hook/tools/relevance per video |
| 4 | metrics | `compute_metrics.py` | metrics.json, selection.json | free (pandas) |
| 5 | transcripts | `fetch_transcripts_comments.py` | transcripts.json, comments.json | free transcripts + 1 unit/video comments |
| 6 | insights | `synthesize_insights.py` | insights.json | Claude: narrative + ideas |
| 7 | deckdata | `build_deck_data.py` | deck_data.json, thumbs/ | free |
| 8 | deck | `build_deck.js` (Node, pptxgenjs) | deck.pptx | free |
| 9 | deliver | `deliver.py` | deck.pdf, delivery.json | Drive + Gmail (free) |

Each Python tool also runs standalone: `.venv/Scripts/python tools/<tool>.py --date YYYY-MM-DD`.

## Design rules (keep them)
- **Numbers come from code, words come from Claude.** `compute_metrics.py` makes every figure; Claude only tags
  videos and writes commentary, and is told to cite only `metrics.json`.
- **Outlier score** = views ÷ median views of the same channel's same-format videos in the window (needs ≥3 videos).
- **Momentum** = topic's share of views-per-day among this week's uploads minus its share among older uploads in the window (percentage points).
- Channel growth uses subscriber deltas once a prior snapshot ≥5 days old exists in `data/history.sqlite`;
  on the first run it falls back to views-per-subscriber.
- `data/history.sqlite` is **persistent**: it stores weekly snapshots and the topic taxonomy. Don't delete it.
  `.tmp/` is disposable.

## Setup (one-time)
1. `python -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt` and `npm install` (pptxgenjs).
2. Google Cloud Console → new project → enable **YouTube Data API v3**, **Google Drive API**, **Gmail API**.
   - Credentials → Create API key → `YOUTUBE_API_KEY` in `.env` (restrict it to YouTube Data API v3).
3. OAuth consent screen: External, add yourself as a test user, then **Publish app → In production**.
   This matters: apps left in *Testing* get refresh tokens that expire after 7 days, which breaks the weekly schedule.
   (Unverified is fine for personal use; you'll click through a warning once.)
   Credentials → Create OAuth client ID → Desktop app → download as `credentials.json` into the project root.
4. `.venv/Scripts/python tools/google_auth.py` → browser consent → creates `token.json`.
5. `ANTHROPIC_API_KEY` and `REPORT_EMAIL` in `.env`.

## Testing the deck without API calls
`.venv/Scripts/python tools/make_demo_data.py && .venv/Scripts/python tools/build_deck_data.py --date demo && node tools/build_deck.js .tmp/run_demo`
then `powershell -File tools/render_slides.ps1 -Deck .tmp/run_demo/deck.pptx` to export PNGs through PowerPoint for visual QA.

## Known constraints and edge cases
- **YouTube quota**: 10,000 units/day by default; newer projects (since June 2026) reportedly also get a separate
  ~100/day `search.list` bucket. Search is the expensive call. On `quotaExceeded` discovery keeps the keywords already
  searched and continues. To cut cost, trim `search_keywords`. Quota usage per step is logged in `quota_log`.
- **Transcripts** use the unofficial `youtube-transcript-api`. YouTube may throttle an IP after many requests.
  Failures are skipped, and the insights step is told when transcripts are missing.
- Only the opening `transcript_word_limit` words (default 2,500) per transcript go to Claude. That covers hooks and structure.
- **Shorts detection** is heuristic: ≤60 s, or ≤180 s with `#short` in the title/tags/description.
- **Seed handles** that don't resolve are logged and skipped. Check the discover log after config edits.
- **Claude**: `claude-opus-5-5` with server-side refusal fallback (`fallbacks: "default"`). Logged spend is about $1–2/run.
  If classification output hits `max_tokens`, lower `BATCH` in `classify_videos.py`.
- **Google token expired / revoked**: the run fails and the alert email can't be sent either. Re-run `tools/google_auth.py`.
- Gmail attachment limit is 25 MB. Decks are typically 2–6 MB with thumbnails.

## Changelog
- 2026-11-16: Initial version.
