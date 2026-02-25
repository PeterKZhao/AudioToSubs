"""
Extract plain text (timestamps removed) from SRT files in OUT_DIR.

Env vars consumed:
    OUT_DIR - directory containing .srt files
"""

import glob
import os
import re


out_dir = os.environ["OUT_DIR"]

for srt_path in sorted(glob.glob(os.path.join(out_dir, "*.srt"))):
    txt_path = os.path.splitext(srt_path)[0] + ".txt"

    if os.path.exists(txt_path):
        print(f"已存在，跳过: {os.path.basename(txt_path)}")
        continue

    with open(srt_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    text_lines: list[str] = []
    for block in re.split(r"\n\s*\n", content.strip()):
        for line in block.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            if re.fullmatch(r"\d+", line):
                continue
            if re.match(r"\d{2}:\d{2}:\d{2},\d{3}\s*-->", line):
                continue
            text_lines.append(line)

    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(text_lines) + "\n")

    print(f"✓ 生成: {os.path.basename(txt_path)} ({len(text_lines)} 行)")

print("纯文本提取完成！")
