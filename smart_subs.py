#!/usr/bin/env python3
"""
智能字幕下载/生成工具
- 有字幕：直接下载并转换为 txt 和 lrc
- 无字幕：Whisper 生成并转换为 txt 和 lrc
"""
import os
import sys
import subprocess
import re
from pathlib import Path
from datetime import timedelta


def run_cmd(cmd, check=True, capture=False):
    """运行命令"""
    print(f"[CMD] {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    if capture:
        result = subprocess.run(cmd, capture_output=True, text=True, check=check)
        return result.stdout, result.stderr
    else:
        subprocess.run(cmd, check=check)
        return None, None


def srt_time_to_seconds(time_str):
    """将 SRT 时间格式转换为秒
    例如: 00:01:23,456 -> 83.456
    """
    time_str = time_str.strip()
    h, m, s = time_str.split(':')
    s, ms = s.split(',')
    total_seconds = int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000
    return total_seconds


def seconds_to_lrc_time(seconds):
    """将秒转换为 LRC 时间格式
    例如: 83.456 -> [01:23.45]
    """
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"[{minutes:02d}:{secs:05.2f}]"


def srt_to_lrc(srt_path, lrc_path):
    """将 SRT 文件转换为 LRC 格式"""
    print(f"转换 {srt_path.name} -> LRC")
    
    with open(srt_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 解析 SRT
    pattern = r'(\d+)\s+(\d{2}:\d{2}:\d{2},\d{3})\s+-->\s+(\d{2}:\d{2}:\d{2},\d{3})\s+(.*?)(?=\n\n|\n*$)'
    matches = re.findall(pattern, content, re.DOTALL)
    
    lrc_lines = []
    for _, start_time, _, text in matches:
        seconds = srt_time_to_seconds(start_time)
        time_tag = seconds_to_lrc_time(seconds)
        # 清理文本（移除多余换行）
        text = text.replace('\n', ' ').strip()
        if text:
            lrc_lines.append(f"{time_tag}{text}")
    
    # 写入 LRC 文件
    with open(lrc_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lrc_lines))
    
    print(f"✓ LRC 已生成: {lrc_path}")


def srt_to_txt(srt_path, txt_path):
    """将 SRT 文件转换为纯文本格式"""
    print(f"转换 {srt_path.name} -> TXT")
    
    with open(srt_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 提取纯文本（去除序号和时间戳）
    pattern = r'(\d+)\s+(\d{2}:\d{2}:\d{2},\d{3})\s+-->\s+(\d{2}:\d{2}:\d{2},\d{3})\s+(.*?)(?=\n\n|\n*$)'
    matches = re.findall(pattern, content, re.DOTALL)
    
    text_lines = []
    for _, _, _, text in matches:
        text = text.strip()
        if text:
            text_lines.append(text)
    
    # 写入 TXT 文件（每行一句）
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(text_lines))
    
    print(f"✓ TXT 已生成: {txt_path}")


def convert_subs_to_all_formats(subs_dir):
    """将所有 SRT 字幕转换为 TXT 和 LRC 格式"""
    print("\n=== 转换字幕格式 ===")
    srt_files = list(Path(subs_dir).glob("*.srt"))
    
    if not srt_files:
        print("警告: 未找到 SRT 文件")
        return
    
    for srt_file in srt_files:
        base_name = srt_file.stem
        
        # 转换为 LRC
        lrc_file = srt_file.parent / f"{base_name}.lrc"
        try:
            srt_to_lrc(srt_file, lrc_file)
        except Exception as e:
            print(f"警告: LRC 转换失败 - {e}")
        
        # 转换为 TXT
        txt_file = srt_file.parent / f"{base_name}.txt"
        try:
            srt_to_txt(srt_file, txt_file)
        except Exception as e:
            print(f"警告: TXT 转换失败 - {e}")


def check_subtitles(url, langs, extra_args):
    """检查视频是否有可用字幕"""
    print("\n=== 检查可用字幕 ===")
    cmd = [
        "yt-dlp",
        "--js-runtimes", "node",
        "--remote-components", "ejs:github",
        "--list-subs",
        url
    ] + extra_args
    
    stdout, stderr = run_cmd(cmd, check=False, capture=True)
    
    # 解析语言列表
    lang_patterns = [re.compile(lang.strip()) for lang in langs.split(',')]
    
    # 检查是否有匹配的字幕
    for line in stdout.split('\n'):
        for pattern in lang_patterns:
            if pattern.search(line):
                print(f"✓ 找到匹配字幕: {line.strip()}")
                return True
    
    print("✗ 未找到匹配的字幕")
    return False


def download_subtitles(url, langs, extra_args, output_dir):
    """下载现有字幕"""
    print("\n=== 下载字幕 ===")
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    cmd = [
        "yt-dlp",
        "--js-runtimes", "node",
        "--remote-components", "ejs:github",
        "--skip-download",
        "--write-subs",
        "--write-auto-subs",
        "--sub-langs", langs,
        "--sub-format", "vtt/best",
        "--convert-subs", "srt",
        "-o", f"{output_dir}/%(title).200s_%(id)s.%(ext)s",
        url
    ] + extra_args
    
    run_cmd(cmd)
    print(f"✓ 字幕已下载到 {output_dir}")


def generate_subtitles(url, model, language, extra_args, audio_dir, output_dir):
    """下载音频并用Whisper生成字幕"""
    print("\n=== 生成字幕（Whisper）===")
    Path(audio_dir).mkdir(parents=True, exist_ok=True)
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    # 1. 下载音频
    print("\n[1/2] 下载音频...")
    cmd = [
        "yt-dlp",
        "--js-runtimes", "node",
        "--remote-components", "ejs:github",
        "-f", "bestaudio/best",
        "-o", f"{audio_dir}/%(title).120B_%(id)s.%(ext)s",
        "--windows-filenames",
        url
    ] + extra_args
    
    run_cmd(cmd)
    
    # 2. 找到音频文件
    audio_files = list(Path(audio_dir).glob("*"))
    if not audio_files:
        raise FileNotFoundError("未找到下载的音频文件")
    audio_file = audio_files[0]
    print(f"✓ 音频文件: {audio_file}")
    
    # 3. Whisper转录（生成 SRT 格式）
    print(f"\n[2/2] Whisper转录（模型: {model}）...")
    cmd = [
        "whisper",
        str(audio_file),
        "--model", model,
        "--output_dir", output_dir,
        "--output_format", "srt",
        "--verbose", "False"
    ]
    
    if language:
        cmd.extend(["--language", language])
    
    run_cmd(cmd)
    print(f"✓ SRT 字幕已生成到 {output_dir}")


def main():
    # 读取环境变量
    url = os.environ.get("URL")
    langs = os.environ.get("LANGS", "zh-Hans,zh-Hant,en.*")
    whisper_model = os.environ.get("WHISPER_MODEL", "small")
    whisper_lang = os.environ.get("WHISPER_LANG", "")
    user_agent = os.environ.get("UA", "")
    
    if not url:
        print("错误: 未提供 URL 环境变量", file=sys.stderr)
        print("使用方法: URL='视频链接' python smart_subs.py", file=sys.stderr)
        sys.exit(1)
    
    print(f"视频 URL: {url}")
    print(f"字幕语言: {langs}")
    print(f"Whisper 模型: {whisper_model}")
    print(f"输出格式: SRT + TXT + LRC")
    
    # 构建通用参数
    extra_args = []
    if Path("cookies.txt").exists():
        extra_args.extend(["--cookies", "cookies.txt"])
        print("✓ 使用 cookies.txt")
    if user_agent:
        extra_args.extend(["--user-agent", user_agent])
        print(f"✓ 使用 User-Agent")
    
    # 主逻辑
    has_subs = check_subtitles(url, langs, extra_args)
    
    if has_subs:
        print("\n>>> 策略：下载现有字幕")
        download_subtitles(url, langs, extra_args, "subs")
    else:
        print("\n>>> 策略：生成字幕（Whisper）")
        generate_subtitles(url, whisper_model, whisper_lang, extra_args, "audio", "subs")
    
    # 转换为所有格式（TXT + LRC）
    convert_subs_to_all_formats("subs")
    
    # 确保输出目录非空
    if not list(Path("subs").glob("*")):
        Path("subs/EMPTY.txt").write_text("No subtitles generated")
    
    print("\n=== 完成 ===")
    print("输出文件:")
    run_cmd(["ls", "-lh", "subs"])


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n[ERROR] {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
