#!/usr/bin/env python3
"""Refresh stats.json with citations and h-index from a Google Scholar profile.

Uses SerpApi when the SERPAPI_KEY environment variable is set, otherwise reads
the public profile page. If anything looks wrong, stats.json is left untouched
and the script exits with an error, so the site keeps its last good figures.
"""
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

AUTHOR_ID = "7Ze3bT8AAAAJ"
STATS_FILE = Path(__file__).resolve().parent / "stats.json"
MAX_DROP = 0.10  # refuse a new citation count more than 10% below the old one


def _get(url):
    request = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        "Accept-Language": "en",
    })
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", "replace")


def parse_serpapi(payload):
    table = json.loads(payload)["cited_by"]["table"]
    merged = {key: value for row in table for key, value in row.items()}
    return int(merged["citations"]["all"]), int(merged["h_index"]["all"])


def parse_profile(html):
    cells = re.findall(r'class="gsc_rsb_std"[^>]*>\s*(\d+)\s*<', html)
    if len(cells) < 4:
        raise ValueError("The citation table was not found. Google Scholar may have blocked the request.")
    return int(cells[0]), int(cells[2])


def fetch_metrics():
    key = os.environ.get("SERPAPI_KEY", "").strip()
    if key:
        query = urllib.parse.urlencode({"engine": "google_scholar_author", "author_id": AUTHOR_ID, "api_key": key})
        return parse_serpapi(_get("https://serpapi.com/search.json?" + query))
    return parse_profile(_get(f"https://scholar.google.com/citations?user={AUTHOR_ID}&hl=en"))


def validated(citations, h_index, old):
    if citations <= 0 or h_index <= 0 or h_index > citations:
        raise ValueError(f"Implausible values: {citations} citations, h-index {h_index}.")
    previous = int(old.get("citations") or 0)
    if previous and citations < previous * (1 - MAX_DROP):
        raise ValueError(f"Citations fell from {previous} to {citations}. Keeping the old value.")
    return citations, h_index


def main():
    old = json.loads(STATS_FILE.read_text(encoding="utf-8")) if STATS_FILE.exists() else {}
    try:
        citations, h_index = validated(*fetch_metrics(), old)
    except Exception as error:  # the site keeps the last good figures
        print(f"Citations not updated: {error}", file=sys.stderr)
        return 1
    stats = {
        "citations": citations,
        "hIndex": h_index,
        "source": "Google Scholar",
        "asOf": datetime.now(timezone.utc).strftime("%B %Y"),
    }
    STATS_FILE.write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
    print(f"Updated: {citations} citations, h-index {h_index}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
