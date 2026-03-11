"""
CI-safe detector for GitHub Actions.

Behavior:
- Same outputs as detect.py: mode, matched_langs, out_dir, video_id
- If yt-dlp metadata fetch fails (e.g. Bilibili 412), do NOT exit non-zero
- Fallback to mode=whisper so downstream steps can continue
"""

import json
import os
import re
import subprocess
from pathlib import Path


def sanitize_url(raw: str) -> str:
    raw = raw.strip()

    # Markdown link: [text](https://...)
    m = re.fullmatch(r"\[[^\]]*\]\((https?://[^)]+)\)", raw)
    if m:
        return m.group(1).strip()

    if raw.startswith(("http://", "https://")):
        return raw

    m = re.search(r"https?://[^\s)]+", raw)
    return m.group(0).strip() if m else raw


def compile_patterns(langs: str):
    out = []
    for x in langs.split(","):
        x = x.strip()
        if not x:
            continue
        try:
            out.append(re.compile(x))
        except re.error:
            out.append(re.compile(re.escape(x)))
    return out


def ok_lang(k: str, patterns) -> bool:
    return any(r.fullmatch(k) or r.search(k) for r in patterns)


def guess_extractor(url: str) -> str:
    u = url.lower()
    if "bilibili.com" in u or "b23.tv" in u:
        return "BiliBili"
    if "youtube.com" in u or "youtu.be" in u:
        return "YouTube"
    return "unknown"


def guess_video_id(url: str) -> str:
    patterns = [
        r"/video/(BV[0-9A-Za-z]+)",
        r"/video/(av\d+)",
        r"[?&]v=([0-9A-Za-z_-]{6,})",
        r"youtu\.be/([0-9A-Za-z_-]{6,})",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return "unknown-id"


def write_outputs(mode: str, matched, out_dir: Path, vid: str):
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
        f.write(f"mode={mode}\n")
        f.write(f"matched_langs={','.join(matched)}\n")
        f.write(f"out_dir={out_dir.as_posix()}\n")
        f.write(f"video_id={vid}\n")

    print("mode         =", mode)
    print("out_dir      =", out_dir)
    print("matched_langs=", ",".join(matched) if matched else "(none)")


url_raw = os.environ["URL"]
url = sanitize_url(url_raw)
langs = os.environ.get("LANGS", "").strip()
ua = os.environ.get("UA", "").strip()
patterns = compile_patterns(langs)

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

try:
    result = subprocess.run(cmd, text=True, capture_output=True, check=True)
    info_text = result.stdout
    info = json.loads(info_text)

    extractor = info.get("extractor_key") or info.get("extractor") or guess_extractor(url)
    channel = info.get("channel_id") or info.get("uploader_id") or info.get("uploader") or "unknown"
    upload_date = info.get("upload_date") or info.get("release_date") or "unknown-date"
    vid = info.get("id") or guess_video_id(url)

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
    matched = [k for k in keys if ok_lang(k, patterns)]
    mode = "download" if matched else "whisper"

    write_outputs(mode, matched, out_dir, vid)

except Exception as e:
    extractor = guess_extractor(url)
    vid = guess_video_id(url)
    out_dir = Path("subs") / extractor / "unknown" / f"unknown-date_{vid}"
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "source_url.txt").write_text(url + "\n", encoding="utf-8")
    (out_dir / "detect_error.txt").write_text(
        f"URL: {url}\n\n"
        f"COMMAND: {' '.join(cmd)}\n\n"
        f"ERROR: {repr(e)}\n",
        encoding="utf-8",
    )

    matched = []
    mode = "whisper"
    write_outputs(mode, matched, out_dir, vid)
