"""Thin YouTube Data API v3 client with quota accounting and retry/backoff.

Quota costs (units): search.list=100, everything else used here=1.
Default allowance: 10,000 units/day (+ a separate ~100/day search bucket on newer projects).
"""
from __future__ import annotations

import time
from typing import Iterable, Iterator

import requests

from common import env, get_logger

log = get_logger("yt")
BASE = "https://www.googleapis.com/youtube/v3"
COST = {"search": 100}


class QuotaExceeded(RuntimeError):
    pass


class YouTube:
    def __init__(self, api_key: str | None = None):
        self.key = api_key or env("YOUTUBE_API_KEY")
        self.units = 0
        self.s = requests.Session()

    def _get(self, endpoint: str, **params) -> dict:
        params = {k: v for k, v in params.items() if v is not None}
        params["key"] = self.key
        for attempt in range(5):
            r = self.s.get(f"{BASE}/{endpoint}", params=params, timeout=30)
            if r.status_code == 200:
                self.units += COST.get(endpoint, 1)
                return r.json()
            reason = ""
            try:
                reason = r.json()["error"]["errors"][0].get("reason", "")
            except Exception:
                pass
            if r.status_code == 403 and reason in ("quotaExceeded", "dailyLimitExceeded"):
                raise QuotaExceeded(f"YouTube quota exhausted on {endpoint} (used ~{self.units} units this run)")
            if r.status_code == 403 and reason == "commentsDisabled":
                return {"items": []}
            if r.status_code == 404:
                return {"items": []}
            if r.status_code in (429, 500, 502, 503, 504):
                wait = 2 ** attempt
                log.warning("%s %s -> %s, retrying in %ss", endpoint, reason, r.status_code, wait)
                time.sleep(wait)
                continue
            raise RuntimeError(f"YouTube API {endpoint} failed {r.status_code}: {r.text[:300]}")
        raise RuntimeError(f"YouTube API {endpoint} failed after retries")

    # ------------------------------------------------------------ endpoints
    def search_videos(self, q: str, published_after: str, max_results: int = 50, order: str = "viewCount") -> list[dict]:
        data = self._get(
            "search", part="snippet", q=q, type="video", order=order,
            publishedAfter=published_after, maxResults=min(max_results, 50),
            relevanceLanguage="en", safeSearch="none",
        )
        return data.get("items", [])

    def channel_by_handle(self, handle: str) -> dict | None:
        handle = handle if handle.startswith("@") else f"@{handle}"
        items = self._get("channels", part="snippet,statistics,contentDetails", forHandle=handle).get("items", [])
        return items[0] if items else None

    def channels(self, ids: Iterable[str]) -> list[dict]:
        out = []
        for chunk in _chunks(list(dict.fromkeys(ids)), 50):
            out += self._get("channels", part="snippet,statistics,contentDetails", id=",".join(chunk), maxResults=50).get("items", [])
        return out

    def playlist_items(self, playlist_id: str, stop_before_iso: str, max_pages: int = 4) -> Iterator[dict]:
        """Yield uploads newest-first until publishedAt < stop_before_iso."""
        token = None
        for _ in range(max_pages):
            data = self._get("playlistItems", part="contentDetails", playlistId=playlist_id, maxResults=50, pageToken=token)
            for it in data.get("items", []):
                pub = it["contentDetails"].get("videoPublishedAt")
                if pub and pub < stop_before_iso:
                    return
                yield it
            token = data.get("nextPageToken")
            if not token:
                return

    def videos(self, ids: Iterable[str]) -> list[dict]:
        out = []
        for chunk in _chunks(list(dict.fromkeys(ids)), 50):
            out += self._get("videos", part="snippet,contentDetails,statistics", id=",".join(chunk), maxResults=50).get("items", [])
        return out

    def top_comments(self, video_id: str, n: int = 50) -> list[dict]:
        data = self._get("commentThreads", part="snippet", videoId=video_id, order="relevance",
                         maxResults=min(n, 100), textFormat="plainText")
        out = []
        for it in data.get("items", []):
            s = it["snippet"]["topLevelComment"]["snippet"]
            out.append({"text": s.get("textDisplay", "")[:600], "likes": s.get("likeCount", 0)})
        return out


def _chunks(seq: list, n: int):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]
