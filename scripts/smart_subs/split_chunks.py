"""
Split large LRC / TXT subtitle files (> MAX_BYTES) into numbered chunks.

Env vars consumed:
    OUT_DIR - directory containing .lrc / .txt files
"""

import glob
import os
import re
from pathlib import Path


out_dir   = os.environ["OUT_DIR"]
MAX_BYTES = 40_000  # UTF-8 字节数阈值


# ── LRC helpers ───────────────────────────────────────────────────────────────

def lrc_text_bytes(content: str) -> int:
    """仅统计歌词文本部分的字节数（不含时间戳）。"""
    return sum(
        len(m.group(3).encode("utf-8"))
        for line in content.strip().splitlines()
        if (m := re.match(r"\[(\d+):(\d+\.\d+)\]\s*(.*)", line))
    )


def split_lrc(lines: list[str], max_bytes: int) -> list[list[str]]:
    chunks: list[list[str]] = []
    cur: list[str] = []
    cur_bytes = 0
    for line in lines:
        m = re.match(r"\[(\d+):(\d+\.\d+)\]\s*(.*)", line.strip())
        if m:
            tbytes = len(m.group(3).encode("utf-8"))
            if cur_bytes + tbytes > max_bytes and cur:
                chunks.append(cur)
                cur, cur_bytes = [line], tbytes
            else:
                cur.append(line)
                cur_bytes += tbytes
        elif cur:
            cur.append(line)
    if cur:
        chunks.append(cur)
    return chunks


# ── TXT helpers ───────────────────────────────────────────────────────────────

def split_txt(lines: list[str], max_bytes: int) -> list[list[str]]:
    chunks: list[list[str]] = []
    cur: list[str] = []
    cur_bytes = 0
    for line in lines:
        lb = len((line + "\n").encode("utf-8"))
        if cur_bytes + lb > max_bytes and cur:
            chunks.append(cur)
            cur, cur_bytes = [line], lb
        else:
            cur.append(line)
            cur_bytes += lb
    if cur:
        chunks.append(cur)
    return chunks


# ── Generic processor ─────────────────────────────────────────────────────────

def process_file(fpath, count_fn, split_fn, subdir_name: str) -> None:
    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    byte_count = count_fn(content)
    fname      = os.path.basename(fpath)
    print(f"检查: {fname}  ({byte_count} 字节)")

    if byte_count <= MAX_BYTES:
        print("  ✓ 无需拆分")
        return

    print(f"  ⚠️  超过 {MAX_BYTES} 字节，开始拆分...")
    chunks_dir = Path(out_dir) / subdir_name
    chunks_dir.mkdir(exist_ok=True)

    lines  = [l.rstrip("\n") for l in content.split("\n")]
    chunks = split_fn(lines, MAX_BYTES)
    base, ext = os.path.splitext(fname)

    for idx, chunk_lines in enumerate(chunks, 1):
        chunk_path = chunks_dir / f"{base}_part{idx}{ext}"
        with open(chunk_path, "w", encoding="utf-8") as f:
            f.write("\n".join(chunk_lines) + "\n")
        print(f"  ✓ {chunk_path.name}  ({count_fn(chr(10).join(chunk_lines))} 字节)")

    print(f"  完成，共 {len(chunks)} 个分片")


# ── Entry point ───────────────────────────────────────────────────────────────

print("=== 处理 LRC 文件 ===")
for fp in sorted(glob.glob(os.path.join(out_dir, "*.lrc"))):
    process_file(fp, lrc_text_bytes, split_lrc, "lrc_chunks")

print("\n=== 处理 TXT 文件 ===")
SKIP = {"source_url.txt"}
for fp in sorted(glob.glob(os.path.join(out_dir, "*.txt"))):
    if os.path.basename(fp) in SKIP:
        continue
    process_file(fp, lambda c: len(c.encode("utf-8")), split_txt, "txt_chunks")

print("\n所有文件处理完成！")
