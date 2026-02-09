#!/usr/bin/env python3
"""
智能字幕下载/生成工具
- 有字幕：直接下载
- 无字幕：Whisper 生成
"""
import os
import sys
import subprocess
import re
from pathlib import Path


def run_cmd(cmd, check=True, capture=False):
    """运行命令"""
    print(f"[CMD] {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    if capture:
        result = subprocess.run(cmd, capture_output=True, text=True, check=check)
        return result.stdout, result.stderr
    else:
        subprocess.run(cmd, check=check)
        return None, None


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
    
    # 3. Whisper转录
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
    print(f"✓ 字幕已生成到 {output_dir}")


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
    
    # 构建通用参数
    extra_args = []
    if Path("cookies.txt").exists():
        extra_args.extend(["--cookies", "cookies.txt"])
        print("✓ 使用 cookies.txt")
    if user_agent:
        extra_args.extend(["--user-agent", user_agent])
        print(f"✓ 使用 User-Agent: {user_agent}")
    
    # 主逻辑
    has_subs = check_subtitles(url, langs, extra_args)
    
    if has_subs:
        print("\n>>> 策略：下载现有字幕")
        download_subtitles(url, langs, extra_args, "subs")
    else:
        print("\n>>> 策略：生成字幕（Whisper）")
        generate_subtitles(url, whisper_model, whisper_lang, extra_args, "audio", "subs")
    
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
