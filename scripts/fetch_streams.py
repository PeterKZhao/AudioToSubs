"""
Fetch YouTube channel streams and build an index.

Required environment variables (set by the workflow):
    CHANNEL_STREAMS_URL  - e.g. https://www.youtube.com/@dlw2023/streams
    CHANNEL_DIR          - safe directory name, e.g. dlw2023
    COOKIES_FILE         - path to Netscape-format cookies.txt
"""

import csv
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path


# ── Config ────────────────────────────────────────────────────────────────────

CHANNEL_URL = os.environ["CHANNEL_STREAMS_URL"]
CHANNEL_DIR = os.environ["CHANNEL_DIR"]
COOKIES     = os.environ["COOKIES_FILE"]
MAX_MD_ROWS = 200

# ── Output paths ──────────────────────────────────────────────────────────────

outdir = Path(f"data/youtube/{CHANNEL_DIR}")
outdir.mkdir(parents=True, exist_ok=True)

flat_path      = outdir / "streams_flat.json"
raw_jsonl_path = outdir / "streams_raw.jsonl"
csv_path       = outdir / "streams_index.csv"
md_path        = outdir / "streams_index.md"
summary_path   = outdir / "summary.json"


# ── Helpers ───────────────────────────────────────────────────────────────────

def yyyymmdd_to_iso(s: str) -> str:
    if not s or len(s) != 8:
        return ""
    return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"


def md_escape(s: str) -> str:
    return (s or "").replace("|", r"\|").replace("\n", " ").strip()


def run_ytdlp(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["yt-dlp", "--cookies", COOKIES, *args],
        capture_output=True,
        text=True,
    )


# ── Step 1: flat-playlist → collect video IDs ─────────────────────────────────

print(f"[1/4] Fetching flat playlist: {CHANNEL_URL}")
flat_result = subprocess.check_output(
    ["yt-dlp", "--cookies", COOKIES, "--flat-playlist", "-J", CHANNEL_URL],
    text=True,
)
flat_path.write_text(flat_result, encoding="utf-8")

flat    = json.loads(flat_result)
entries = flat.get("entries") or []
ids: list[str] = []
seen: set[str] = set()
for e in entries:
    vid = (e or {}).get("id")
    if vid and vid not in seen:
        seen.add(vid)
        ids.append(vid)

print(f"    Found {len(ids)} video IDs")


# ── Step 2: fetch full metadata per video ─────────────────────────────────────

print(f"[2/4] Fetching metadata for each video …")
raw_lines: list[str] = []
for i, vid in enumerate(ids, 1):
    url = f"https://www.youtube.com/watch?v={vid}"
    p   = run_ytdlp("--skip-download", "--ignore-no-formats-error", "-j", url)
    if p.returncode != 0 or not p.stdout.strip():
        print(f"    [{i}/{len(ids)}] SKIP {vid} (no metadata)")
        continue
    for line in p.stdout.splitlines():
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            raw_lines.append(line)
    if i % 20 == 0:
        print(f"    [{i}/{len(ids)}] processed …")

raw_jsonl_path.write_text(
    "\n".join(raw_lines) + ("\n" if raw_lines else ""),
    encoding="utf-8",
)


# ── Step 3: parse & sort rows ─────────────────────────────────────────────────

print("[3/4] Parsing metadata …")
rows: list[dict] = []
for line in raw_lines:
    d            = json.loads(line)
    availability = d.get("availability") or ""
    members_only = availability == "subscriber_only"
    upload_date  = d.get("upload_date") or d.get("release_date") or ""
    rows.append({
        "id"          : d.get("id") or "",
        "title"       : d.get("fulltitle") or d.get("title") or "",
        "url"         : d.get("webpage_url") or f"https://www.youtube.com/watch?v={d.get('id', '')}",
        "upload_date" : yyyymmdd_to_iso(upload_date),
        "live_status" : d.get("live_status") or "",
        "was_live"    : bool(d.get("was_live")) if d.get("was_live") is not None else "",
        "is_live"     : bool(d.get("is_live"))  if d.get("is_live")  is not None else "",
        "availability": availability,
        "members_only": members_only,
    })

rows.sort(key=lambda r: (r["upload_date"] or "0000-00-00", r["id"]), reverse=True)


# ── Step 4: write outputs ─────────────────────────────────────────────────────

print("[4/4] Writing output files …")

# CSV
FIELDNAMES = ["id", "title", "url", "upload_date", "live_status",
              "was_live", "is_live", "availability", "members_only"]
with csv_path.open("w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
    writer.writeheader()
    writer.writerows(rows)

# Markdown
channel_label = CHANNEL_URL.split("youtube.com/")[-1].split("/")[0]
now_utc       = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
md_lines = [
    f"# {channel_label} Streams Index\n",
    f"- Source: {CHANNEL_URL}\n",
    f"- Updated (UTC): {now_utc}\n",
    f"- Total entries: {len(rows)}\n",
    "",
    "| Date | Members | Live status | Title | URL |",
    "|---|---:|---|---|---|",
]
for r in rows[:MAX_MD_ROWS]:
    md_lines.append(
        f"| {r['upload_date'] or ''} "
        f"| {'Y' if r['members_only'] else 'N'} "
        f"| {md_escape(r['live_status'])} "
        f"| {md_escape(r['title'])} "
        f"| {md_escape(r['url'])} |"
    )
md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

# Summary
summary = {
    "channel_streams_url" : CHANNEL_URL,
    "updated_utc"         : datetime.now(timezone.utc).isoformat(),
    "total_entries"       : len(rows),
    "members_only_count"  : sum(1 for r in rows if r["members_only"]),
    "public_count"        : sum(1 for r in rows if not r["members_only"]),
}
summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

print(f"\n✓ Done — {len(rows)} entries written to {outdir}/")
