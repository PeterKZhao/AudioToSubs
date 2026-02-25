"""
Resolve per-video output directory and detect subtitle availability.

Env vars consumed:
    URL           - video URL
    LANGS         - comma-separated language patterns (regex supported)
    UA            - optional User-Agent string
    GITHUB_OUTPUT - set automatically by GitHub Actions runner
"""

import json
import os
import re
import subprocess
from pathlib import Path


url      = os.environ["URL"].strip()
langs    = os.environ.get("LANGS", "").strip()
ua       = os.environ.get("UA", "").strip()
patterns = [re.compile(x.strip()) for x in langs.split(",") if x.strip()]

cmd = [
    "yt-dlp",
    "--js-runtimes", "node",
    "--remote-components", "ejs:github",
    "--skip-download",
    "--write-auto-subs",
    "-J",
    url,
]
if os.path.exists("cookies.txt"):
    cmd += ["--cookies", "cookies.txt"]
if ua:
    cmd += ["--user-agent", ua]

info_text = subprocess.check_output(cmd, text=True)
info      = json.loads(info_text)

extractor   = info.get("extractor_key") or info.get("extractor") or "unknown"
channel     = info.get("channel_id") or info.get("uploader_id") or info.get("uploader") or "unknown"
upload_date = info.get("upload_date") or info.get("release_date") or "unknown-date"
vid         = info.get("id") or "unknown-id"

out_dir = Path("subs") / extractor / channel / f"{upload_date}_{vid}"
out_dir.mkdir(parents=True, exist_ok=True)

(out_dir / "source_url.txt").write_text(url + "\n", encoding="utf-8")
(out_dir / "info.json").write_text(
    info_text + ("" if info_text.endswith("\n") else "\n"),
    encoding="utf-8",
)

subs = info.get("subtitles") or {}
auto = info.get("automatic_captions") or {}
keys = sorted(set(list(subs.keys()) + list(auto.keys())))


def ok(k: str) -> bool:
    return any(r.fullmatch(k) or r.search(k) for r in patterns)


matched = [k for k in keys if ok(k)]
mode    = "download" if matched else "whisper"

with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
    f.write(f"mode={mode}\n")
    f.write(f"matched_langs={','.join(matched)}\n")
    f.write(f"out_dir={out_dir.as_posix()}\n")
    f.write(f"video_id={vid}\n")

print("mode         =", mode)
print("out_dir      =", out_dir)
print("matched_langs=", ",".join(matched) if matched else "(none)")
