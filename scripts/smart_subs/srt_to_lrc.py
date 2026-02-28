"""Convert SRT files in OUT_DIR to LRC format."""
import os, re
from pathlib import Path

out_dir = Path(os.environ["OUT_DIR"])

def srt_time_to_lrc(t: str) -> str:
    h, m, rest = t.split(":")
    s, ms = rest.replace(",", ".").split(".")
    total_min = int(h) * 60 + int(m)
    return f"[{total_min:02d}:{int(s):02d}.{ms[:2]}]"

for srt in out_dir.glob("*.srt"):
    blocks = re.split(r"\n\n+", srt.read_text(encoding="utf-8").strip())
    lrc_lines = []
    for block in blocks:
        lines = block.strip().splitlines()
        if len(lines) < 3:
            continue
        times = lines[1].split(" --> ")
        tag = srt_time_to_lrc(times[0].strip())
        text = " ".join(lines[2:])
        lrc_lines.append(f"{tag}{text}")
    lrc_path = srt.with_suffix(".lrc")
    lrc_path.write_text("\n".join(lrc_lines) + "\n", encoding="utf-8")
    print(f"Wrote {lrc_path}")
