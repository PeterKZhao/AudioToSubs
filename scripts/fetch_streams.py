"""
Fetch YouTube channel streams + videos and build a combined index.

Required environment variables (set by the workflow):
    CHANNEL_URL   - e.g. https://www.youtube.com/@zrzjpl
    CHANNEL_DIR   - safe directory name, e.g. zrzjpl
    COOKIES_FILE  - path to Netscape-format cookies.txt (can be empty)
"""

import csv
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path


# ── Config ────────────────────────────────────────────────────────────────────

CHANNEL_URL = os.environ["CHANNEL_URL"].rstrip("/")
CHANNEL_DIR = os.environ["CHANNEL_DIR"]
COOKIES = os.environ["COOKIES_FILE"]

TABS = ("streams", "videos")
MAX_MD_ROWS = 200

# ── Output paths ──────────────────────────────────────────────────────────────

outdir = Path(f"data/youtube/{CHANNEL_DIR}")
outdir.mkdir(parents=True, exist_ok=True)

flat_path = outdir / "streams_flat.json"
raw_jsonl_path = outdir / "streams_raw.jsonl"
csv_path = outdir / "streams_index.csv"
md_path = outdir / "streams_index.md"
summary_path = outdir / "summary.json"


# ── Helpers ───────────────────────────────────────────────────────────────────

def yyyymmdd_to_iso(s: str) -> str:
    if not s or len(s) != 8:
        return ""
    return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"


def ts_to_iso_date(ts) -> str:
    if ts in (None, ""):
        return ""
    try:
        return datetime.fromtimestamp(int(ts), timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return ""


def md_escape(s: str) -> str:
    return (s or "").replace("|", r"\|").replace("\n", " ").strip()


def run_ytdlp(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["yt-dlp", "--cookies", COOKIES, *args],
        capture_output=True,
        text=True,
    )


# ── Step 1: flat-playlist → collect IDs from /streams and /videos ────────────

print(f"[1/4] Fetching flat playlists from tabs: {', '.join(TABS)}")

flat_dump = {}
video_tabs: dict[str, set[str]] = {}
errors: list[str] = []

for tab in TABS:
    tab_url = f"{CHANNEL_URL}/{tab}"
    print(f"    - {tab_url}")

    p = run_ytdlp("--flat-playlist", "-J", tab_url)
    if p.returncode != 0 or not p.stdout.strip():
        err = (p.stderr or "").strip()
        flat_dump[tab] = {
            "tab_url": tab_url,
            "error": err,
            "entries": [],
        }
        errors.append(f"{tab}: {err[:300]}")
        print(f"      WARN: failed to fetch {tab}")
        continue

    try:
        flat = json.loads(p.stdout)
    except json.JSONDecodeError as e:
        flat_dump[tab] = {
            "tab_url": tab_url,
            "error": f"JSON decode error: {e}",
            "entries": [],
        }
        errors.append(f"{tab}: JSON decode error: {e}")
        print(f"      WARN: invalid JSON for {tab}")
        continue

    flat_dump[tab] = flat
    entries = flat.get("entries") or []

    found = 0
    for e in entries:
        vid = (e or {}).get("id")
        if not vid:
            continue
        found += 1
        video_tabs.setdefault(vid, set()).add(tab)

    print(f"      Found {found} IDs in {tab}")

flat_path.write_text(
    json.dumps(flat_dump, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)

if not video_tabs:
    joined = " | ".join(errors) if errors else "No entries found"
    raise SystemExit(f"No video IDs fetched from any tab. Details: {joined}")

print(f"    Total unique video IDs across tabs: {len(video_tabs)}")


# ── Step 2: fetch full metadata per unique video ──────────────────────────────

print("[2/4] Fetching metadata for each unique video …")

raw_lines: list[str] = []
items = list(video_tabs.items())

for i, (vid, tabs) in enumerate(items, 1):
    url = f"https://www.youtube.com/watch?v={vid}"
    p = run_ytdlp("--skip-download", "--ignore-no-formats-error", "-j", url)

    if p.returncode != 0 or not p.stdout.strip():
        print(f"    [{i}/{len(items)}] SKIP {vid} (no metadata)")
        continue

    metadata_line = None
    for line in p.stdout.splitlines():
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            metadata_line = line
            break

    if not metadata_line:
        print(f"    [{i}/{len(items)}] SKIP {vid} (invalid metadata)")
        continue

    d = json.loads(metadata_line)
    ordered_tabs = [t for t in TABS if t in tabs]
    d["_source_tabs"] = ordered_tabs
    raw_lines.append(json.dumps(d, ensure_ascii=False))

    if i % 20 == 0:
        print(f"    [{i}/{len(items)}] processed …")

raw_jsonl_path.write_text(
    "\n".join(raw_lines) + ("\n" if raw_lines else ""),
    encoding="utf-8",
)


# ── Step 3: parse & sort rows ─────────────────────────────────────────────────

print("[3/4] Parsing metadata …")

rows: list[dict] = []

for line in raw_lines:
    d = json.loads(line)

    source_tabs = d.get("_source_tabs") or []
    source_primary = source_tabs[0] if source_tabs else ""

    availability = d.get("availability") or ""
    members_only = availability == "subscriber_only"

    upload_date_raw = d.get("upload_date") or d.get("release_date") or ""
    upload_date = yyyymmdd_to_iso(upload_date_raw)
    if not upload_date:
        upload_date = ts_to_iso_date(d.get("release_timestamp") or d.get("timestamp"))

    rows.append({
        "id": d.get("id") or "",
        "title": d.get("fulltitle") or d.get("title") or "",
        "url": d.get("webpage_url") or f"https://www.youtube.com/watch?v={d.get('id', '')}",
        "upload_date": upload_date,
        "source_primary": source_primary,
        "source_tabs": ",".join(source_tabs),
        "live_status": d.get("live_status") or "",
        "was_live": bool(d.get("was_live")) if d.get("was_live") is not None else "",
        "is_live": bool(d.get("is_live")) if d.get("is_live") is not None else "",
        "availability": availability,
        "members_only": members_only,
    })

rows.sort(key=lambda r: (r["upload_date"] or "0000-00-00", r["id"]), reverse=True)


# ── Step 4: write outputs ─────────────────────────────────────────────────────

print("[4/4] Writing output files …")

FIELDNAMES = [
    "id",
    "title",
    "url",
    "upload_date",
    "source_primary",
    "source_tabs",
    "live_status",
    "was_live",
    "is_live",
    "availability",
    "members_only",
]

with csv_path.open("w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
    writer.writeheader()
    writer.writerows(rows)

now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
tab_counts = {
    tab: sum(1 for r in rows if tab in (r["source_tabs"].split(",") if r["source_tabs"] else []))
    for tab in TABS
}

md_lines = [
    f"# {CHANNEL_DIR} Streams/Videos Index\n",
    f"- Channel: {CHANNEL_URL}\n",
    f"- Included tabs: {', '.join(TABS)}\n",
    f"- Updated (UTC): {now_utc}\n",
    f"- Total unique entries: {len(rows)}\n",
    f"- Entries tagged streams: {tab_counts['streams']}\n",
    f"- Entries tagged videos: {tab_counts['videos']}\n",
    "",
    "| Date | Tabs | Members | Live status | Title | URL |",
    "|---|---|---:|---|---|---|",
]

for r in rows[:MAX_MD_ROWS]:
    md_lines.append(
        f"| {r['upload_date'] or ''} "
        f"| {md_escape(r['source_tabs'])} "
        f"| {'Y' if r['members_only'] else 'N'} "
        f"| {md_escape(r['live_status'])} "
        f"| {md_escape(r['title'])} "
        f"| {md_escape(r['url'])} |"
    )

md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

summary = {
    "channel_url": CHANNEL_URL,
    "included_tabs": list(TABS),
    "updated_utc": datetime.now(timezone.utc).isoformat(),
    "total_unique_entries": len(rows),
    "tab_counts": tab_counts,
    "members_only_count": sum(1 for r in rows if r["members_only"]),
    "public_count": sum(1 for r in rows if not r["members_only"]),
}

summary_path.write_text(
    json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)

print(f"\n✓ Done — {len(rows)} unique entries written to {outdir}/")
