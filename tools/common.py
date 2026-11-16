"""Shared helpers: paths, config, env, logging, run directory, JSON IO, SQLite history."""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "niche.yaml"
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "history.sqlite"
TMP_DIR = ROOT / ".tmp"

load_dotenv(ROOT / ".env")

# Scheduled runs redirect stdout to a log file; Windows would default to cp1252 and choke on non-ASCII.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s %(message)s", "%H:%M:%S"))
        logger.addHandler(h)
        logger.setLevel(logging.INFO)
    return logger


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def env(name: str, required: bool = True) -> str | None:
    val = os.getenv(name)
    if required and not val:
        raise RuntimeError(f"Missing {name} in .env — see workflows/youtube_weekly_insights.md (Setup).")
    return val


def run_dir(run_date: str | None = None) -> Path:
    """Per-run scratch folder: .tmp/run_YYYY-MM-DD/"""
    d = TMP_DIR / f"run_{run_date or date.today().isoformat()}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def as_date(run_date: str | None) -> date:
    """Run labels are normally YYYY-MM-DD; non-date labels (e.g. 'demo', 'test') mean today."""
    try:
        return date.fromisoformat(run_date) if run_date else date.today()
    except ValueError:
        return date.today()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, default=str)


def read_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def parse_run_date_arg(argv: list[str] | None = None) -> str | None:
    """Tools accept an optional --date YYYY-MM-DD to target an existing run folder."""
    argv = argv if argv is not None else sys.argv[1:]
    if "--date" in argv:
        return argv[argv.index("--date") + 1]
    return None


# ---------------------------------------------------------------- history DB
SCHEMA = """
CREATE TABLE IF NOT EXISTS channels (
    channel_id TEXT PRIMARY KEY,
    title TEXT, handle TEXT, thumbnail TEXT, uploads_playlist TEXT,
    source TEXT, first_seen TEXT, last_seen TEXT
);
CREATE TABLE IF NOT EXISTS channel_snapshots (
    channel_id TEXT, snapshot_date TEXT,
    subscribers INTEGER, total_views INTEGER, video_count INTEGER,
    PRIMARY KEY (channel_id, snapshot_date)
);
CREATE TABLE IF NOT EXISTS video_snapshots (
    video_id TEXT, snapshot_date TEXT, channel_id TEXT, title TEXT,
    published_at TEXT, duration_s INTEGER, is_short INTEGER,
    views INTEGER, likes INTEGER, comments INTEGER,
    PRIMARY KEY (video_id, snapshot_date)
);
CREATE TABLE IF NOT EXISTS topic_taxonomy (
    snapshot_date TEXT, topic TEXT, description TEXT,
    PRIMARY KEY (snapshot_date, topic)
);
CREATE TABLE IF NOT EXISTS quota_log (
    snapshot_date TEXT, step TEXT, units INTEGER
);
"""


def db() -> sqlite3.Connection:
    DATA_DIR.mkdir(exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.executescript(SCHEMA)
    return con
