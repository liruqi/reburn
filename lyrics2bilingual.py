#!/usr/bin/env python3
"""
lyrics2bilingual.py — 从歌词文本生成双语字幕并烧录到视频

用法:
  python lyrics2bilingual.py --video "D:/path/to/video.webm" --lyrics lyrics.txt --source-lang th --target-lang zh-CN

歌词文件格式:
  - 空行分隔的段落，每段对应一条字幕
  - 段内换行用 \\n 或直接在歌词文件中换行
  - 可选: 在每段前加 [MM:SS] 时间标记，如 [00:08] 表示该段从 8 秒开始

功能:
  1. 解析歌词文件，生成 SRT 字幕
  2. 如果没有时间标记，分析音频能量自动分配时间轴
  3. 调用 JZSub 的 subtitle_pipeline.py 进行翻译流水线
  4. 渲染双语 ASS/SRT 字幕
  5. 调用 burn_subtitles.py 烧录到视频

依赖:
  - JZSub skill 脚本 (subtitle_pipeline.py, burn_subtitles.py, verify_delivery.py)
  - ffmpeg/ffprobe (带 libass 支持)
  - Python 3.10+
"""

from __future__ import annotations

import argparse
import json
import os
import re
import struct
import subprocess
import sys
import tempfile
import wave
from pathlib import Path
from typing import Any, List, Optional, Tuple


# ── 路径常量 ──────────────────────────────────────────────

SKILL_DIR = Path.home() / ".workbuddy-ai" / "skills" / "jzsub"
SCRIPTS_DIR = SKILL_DIR / "scripts"
SUBTITLE_PIPELINE = SCRIPTS_DIR / "subtitle_pipeline.py"
BURN_SUBTITLES = SCRIPTS_DIR / "burn_subtitles.py"
VERIFY_DELIVERY = SCRIPTS_DIR / "verify_delivery.py"

# FFmpeg 路径（自动检测）
FFMPEG_CANDIDATES = [
    Path.home() / ".workbuddy-ai" / "binaries" / "ffmpeg" / "ffmpeg-master-latest-win64-gpl" / "bin",
]
PYTHON_BIN = Path.home() / ".workbuddy-ai" / "binaries" / "python" / "versions" / "3.13.12" / "python.exe"


def find_ffmpeg() -> Tuple[Path, Path]:
    """找到 ffmpeg 和 ffprobe 可执行文件。"""
    # 1. 检查 PATH
    for name in ("ffmpeg", "ffmpeg.exe"):
        path = _which(name)
        if path:
            ff = Path(path)
            fp = ff.parent / ("ffprobe" + ff.suffix)
            if fp.is_file():
                return ff, fp
    # 2. 检查候选路径
    for cand in FFMPEG_CANDIDATES:
        ff = cand / "ffmpeg.exe"
        fp = cand / "ffprobe.exe"
        if ff.is_file() and fp.is_file():
            return ff, fp
    raise FileNotFoundError("找不到 ffmpeg/ffprobe，请安装后加入 PATH 或放到候选目录")


def _which(name: str) -> Optional[str]:
    """在 PATH 中查找可执行文件。"""
    result = subprocess.run(
        ["where" if sys.platform == "win32" else "which", name],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        lines = result.stdout.strip().splitlines()
        return lines[0] if lines else None
    return None


def get_python() -> str:
    """获取可用的 Python 解释器路径。"""
    # 优先使用 managed Python
    if PYTHON_BIN.is_file():
        return str(PYTHON_BIN)
    return sys.executable


def get_video_duration(video_path: Path, ffprobe: Path) -> float:
    """用 ffprobe 获取视频时长（秒）。"""
    result = subprocess.run(
        [str(ffprobe), "-v", "quiet", "-print_format", "json", "-show_format", str(video_path)],
        capture_output=True, text=True, check=True
    )
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


# ── 歌词解析 ─────────────────────────────────────────────

TIME_MARKER_RE = re.compile(r'^\[(\d{1,2}):(\d{2})(?:[.,](\d{1,3}))?\]')


def parse_lyrics(lyrics_text: str) -> List[dict]:
    """
    解析歌词文本，返回段落列表。
    
    每段格式:
        {"text": "泰语歌词行1\n泰语歌词行2", "start": 8.0 (可选), "end": 18.0 (可选)}
    
    段落用空行分隔。
    如果段首有 [MM:SS] 标记，则用该时间作为开始时间。
    """
    blocks = re.split(r'\n\s*\n', lyrics_text.strip())
    segments = []
    
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        
        start = None
        time_match = TIME_MARKER_RE.match(block)
        if time_match:
            mm = int(time_match.group(1))
            ss = int(time_match.group(2))
            ms_str = time_match.group(3) or '0'
            ms = int(ms_str.ljust(3, '0'))
            start = mm * 60 + ss + ms / 1000
            block = block[time_match.end():].strip()
        
        segments.append({
            'text': block,
            'start': start,
            'end': None
        })
    
    return segments


# ── 音频分析（自动时间轴）────────────────────────────────

def extract_audio(video_path: Path, ffmpeg: Path, output_wav: Path) -> None:
    """从视频提取单声道 8kHz WAV 用于能量分析。"""
    subprocess.run(
        [str(ffmpeg), "-y", "-i", str(video_path),
         "-vn", "-ac", "1", "-ar", "8000", "-c:a", "pcm_s16le", str(output_wav)],
        capture_output=True, check=True
    )


def analyze_audio_energy(wav_path: Path, window_ms: int = 100) -> List[float]:
    """计算音频每 window_ms 毫秒的 RMS 能量。"""
    with wave.open(str(wav_path), 'rb') as wav:
        n_frames = wav.getnframes()
        sample_rate = wav.getframerate()
        raw = wav.readframes(n_frames)
    
    samples = struct.unpack(f'<{n_frames}h', raw)
    window_size = int(sample_rate * window_ms / 1000)
    n_windows = len(samples) // window_size
    
    energies = []
    for i in range(n_windows):
        chunk = samples[i * window_size : (i + 1) * window_size]
        sum_sq = sum(s * s for s in chunk)
        rms = (sum_sq / len(chunk)) ** 0.5
        energies.append(rms)
    
    return energies


def find_vocal_segments_boundaries(
    energies: List[float],
    n_segments: int,
    duration: float,
    intro_end_hint: float = 8.0,
    outro_start_hint: Optional[float] = None,
    window_ms: int = 100
) -> List[Tuple[float, float]]:
    """
    根据音频能量分布，将时长分成 n_segments 个段落。
    
    策略:
    1. 前奏（低能量区域）结束后才开始第一段
    2. 根据能量变化找到自然的分割点
    3. 每段时长尽量均匀，但在能量骤降处分割
    """
    n_windows = len(energies)
    window_sec = window_ms / 1000
    
    # 确定有效音频范围（跳过前奏和尾奏）
    avg_energy = sum(energies) / n_windows
    threshold = avg_energy * 0.15
    
    # 找到第一个超过阈值的窗口
    first_active = 0
    for i, e in enumerate(energies):
        if e > threshold:
            first_active = i
            break
    
    intro_end = max(first_active * window_sec, intro_end_hint)
    
    # 找到最后一个超过阈值的窗口
    last_active = n_windows - 1
    for i in range(n_windows - 1, -1, -1):
        if energies[i] > threshold:
            last_active = i
            break
    
    if outro_start_hint:
        outro_start = outro_start_hint
    else:
        outro_start = (last_active + 1) * window_sec
    
    active_duration = outro_start - intro_end
    
    # 简单策略：均匀分割，但在能量低谷处微调
    avg_seg_duration = active_duration / n_segments
    
    boundaries = []
    for i in range(n_segments):
        start = intro_end + i * avg_seg_duration
        end = intro_end + (i + 1) * avg_seg_duration
        
        # 在分割点附近找能量低谷（±2秒范围）
        target_window = int(end / window_sec)
        search_range = int(2.0 / window_sec)  # ±2秒
        
        low_window = target_window
        low_energy = float('inf')
        for j in range(max(0, target_window - search_range),
                      min(n_windows, target_window + search_range)):
            if energies[j] < low_energy:
                low_energy = energies[j]
                low_window = j
        
        adjusted_end = low_window * window_sec
        if i < n_segments - 1:
            end = adjusted_end
        
        boundaries.append((start, end))
    
    # 确保最后一段结束于 outro_start
    if boundaries:
        last = boundaries[-1]
        boundaries[-1] = (last[0], outro_start)
    
    return boundaries


# ── SRT 生成 ─────────────────────────────────────────────

def format_srt_time(seconds: float) -> str:
    """将秒数格式化为 SRT 时间码 HH:MM:SS,mmm。"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    ms = int((seconds * 1000) % 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def generate_srt(segments: List[dict], boundaries: List[Tuple[float, float]], output_path: Path) -> None:
    """从歌词段落和时间边界生成 SRT 文件。"""
    lines = []
    for i, (seg, (start, end)) in enumerate(zip(segments, boundaries), 1):
        lines.append(str(i))
        lines.append(f"{format_srt_time(start)} --> {format_srt_time(end)}")
        lines.append(seg['text'])
        lines.append('')
    
    output_path.write_text('\n'.join(lines), encoding='utf-8')


# ── JZSub 流水线调用 ─────────────────────────────────────

def run_jzsub_pipeline(
    video_path: Path,
    srt_path: Path,
    job_dir: Path,
    source_lang: str,
    target_lang: str,
    translations: List[str],
    ffmpeg: Path,
    ffprobe: Path,
    burn_preset: str = "ultrafast",
    burn_crf: int = 23,
    allow_missing_font: bool = True,
) -> Path:
    """
    运行完整的 JZSub 字幕流水线:
    1. prepare — 创建 manifest
    2. next-batch + translate — 翻译
    3. render — 渲染双语字幕
    4. burn — 烧录到视频
    返回烧录后的 MP4 路径。
    """
    python = get_python()
    env = os.environ.copy()
    env["PATH"] = os.pathsep.join([str(ffmpeg.parent), env.get("PATH", "")])
    
    work_dir = job_dir / "subtitles"
    work_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Prepare
    print("[1/5] 准备字幕 manifest...")
    result = subprocess.run(
        [python, str(SUBTITLE_PIPELINE), "prepare",
         "--work-dir", str(work_dir),
         "--source-language", source_lang,
         "--target-language", target_lang,
         str(srt_path)],
        capture_output=True, text=True, env=env, check=True
    )
    manifest_path = work_dir / "subtitle-manifest.json"
    print(f"  manifest: {manifest_path}")
    
    # 2. Translate batches
    print("[2/5] 翻译字幕...")
    translation_output_dir = work_dir / "translation-output"
    translation_output_dir.mkdir(parents=True, exist_ok=True)
    
    batch_num = 0
    while True:
        result = subprocess.run(
            [python, str(SUBTITLE_PIPELINE), "next-batch",
             "--manifest", str(manifest_path)],
            capture_output=True, text=True, env=env, check=True
        )
        data = json.loads(result.stdout)
        
        if data.get("done"):
            break
        
        batch = data["batch"]
        batch_num += 1
        output_path = Path(data["output_path"])
        
        # 调用翻译函数（由调用方提供翻译）
        translations_result = {"translations": []}
        for item in batch["items"]:
            idx = int(item["id"].split("-")[1]) - 1
            if idx < len(translations):
                translations_result["translations"].append({
                    "id": item["id"],
                    "translation": translations[idx]
                })
            else:
                raise ValueError(f"翻译 {idx+1} 缺失，只有 {len(translations)} 条翻译")
        
        output_path.write_text(
            json.dumps(translations_result, ensure_ascii=False),
            encoding='utf-8'
        )
        print(f"  批次 {batch_num}: {len(translations_result['translations'])} 条翻译")
    
    # 3. Render
    print("[3/5] 渲染双语字幕...")
    rendered_dir = work_dir / "rendered"
    result = subprocess.run(
        [python, str(SUBTITLE_PIPELINE), "render",
         "--manifest", str(manifest_path),
         "--translations-dir", str(translation_output_dir),
         "--output-dir", str(rendered_dir)],
        capture_output=True, text=True, env=env, check=True
    )
    print(f"  渲染完成: {rendered_dir}")
    
    # 4. Burn
    print("[4/5] 烧录字幕到视频...")
    ass_path = rendered_dir / "bilingual.ass"
    
    # 从视频文件名生成输出名
    video_stem = video_path.stem
    # 如果文件名是 YouTube ID 格式，用默认名称
    if re.match(r'^[A-Za-z0-9_-]{11}$', video_stem):
        # 尝试从 SRT 第一行获取歌曲名
        first_line = srt_path.read_text(encoding='utf-8').split('\n')[2] if srt_path.exists() else ""
        title = first_line.split('\n')[0][:30] if first_line else video_stem
        burn_output = job_dir / f"双语字幕版「{title}」.mp4"
    else:
        burn_output = job_dir / f"双语字幕版_{video_stem}.mp4"
    
    burn_cmd = [
        python, str(BURN_SUBTITLES),
        str(video_path), str(ass_path), str(burn_output),
        "--force", f"--preset", burn_preset, f"--crf", str(burn_crf),
    ]
    if allow_missing_font:
        burn_cmd.append("--allow-missing-font")
    
    # 烧录是长时间运行，直接输出到终端
    proc = subprocess.Popen(burn_cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    for line in proc.stdout:
        print(line, end='')
    proc.wait()
    if proc.returncode != 0:
        stderr = proc.stderr.read()
        raise RuntimeError(f"烧录失败: {stderr}")
    
    print(f"  烧录完成: {burn_output}")
    
    # 5. Verify
    print("[5/5] 验证交付...")
    manifest_json = {
        "output_directory": str(job_dir),
        "deliverable": "full",
        "delivery_names": {"bilingual_video": burn_output.name},
        "artifacts": {
            "lossless_mp4_master": {"path": str(video_path)},
            "subtitle": {
                "source_srt": {"path": "subtitles/source.original.srt"},
                "language": source_lang,
                "kind": "manual",
                "dialogue": True
            }
        }
    }
    download_manifest = job_dir / "download-manifest.json"
    download_manifest.write_text(json.dumps(manifest_json, ensure_ascii=False, indent=2), encoding='utf-8')
    
    result = subprocess.run(
        [python, str(VERIFY_DELIVERY), str(download_manifest)],
        capture_output=True, text=True, env=env, check=True
    )
    verify_data = json.loads(result.stdout)
    if verify_data.get("complete"):
        print(f"  ✓ 验证通过: {verify_data['stage']}")
    else:
        print(f"  ✗ 验证失败: {verify_data}")
    
    return burn_output


# ── 主函数 ───────────────────────────────────────────────

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="从歌词文本生成双语字幕并烧录到视频"
    )
    parser.add_argument("--video", required=True, type=Path, help="输入视频文件路径")
    parser.add_argument("--lyrics", required=True, type=Path, help="歌词文本文件路径")
    parser.add_argument("--source-lang", default="th", help="源语言代码 (默认: th)")
    parser.add_argument("--target-lang", default="zh-CN", help="目标语言代码 (默认: zh-CN)")
    parser.add_argument("--translations", type=Path, help="翻译文本文件（每行一条翻译，顺序对应歌词段落）")
    parser.add_argument("--job-dir", type=Path, help="工作目录（默认: 在视频旁创建 jzsub-jobs/<视频名>/）")
    parser.add_argument("--preset", default="ultrafast", help="ffmpeg 编码预设 (默认: ultrafast)")
    parser.add_argument("--crf", type=int, default=23, help="ffmpeg CRF 质量值 (默认: 23)")
    parser.add_argument("--allow-missing-font", action="store_true", default=True,
                        help="允许字体替换 (默认: 开启)")
    parser.add_argument("--intro-end", type=float, default=None,
                        help="前奏结束时间（秒），覆盖自动检测")
    
    args = parser.parse_args(argv)
    
    # 检查依赖
    ffmpeg, ffprobe = find_ffmpeg()
    print(f"ffmpeg: {ffmpeg}")
    print(f"ffprobe: {ffprobe}")
    
    # 设置工作目录
    video_path = args.video.resolve()
    if args.job_dir:
        job_dir = args.job_dir.resolve()
    else:
        job_dir = video_path.parent / "jzsub-jobs" / video_path.stem
    job_dir.mkdir(parents=True, exist_ok=True)
    
    # 读取歌词
    lyrics_text = args.lyrics.read_text(encoding='utf-8')
    segments = parse_lyrics(lyrics_text)
    print(f"解析到 {len(segments)} 段歌词")
    
    # 获取视频时长
    duration = get_video_duration(video_path, ffprobe)
    print(f"视频时长: {duration:.1f}s ({int(duration//60)}:{int(duration%60):02d})")
    
    # 确定时间轴
    has_timestamps = all(s.get('start') is not None for s in segments)
    
    if has_timestamps:
        # 使用歌词中的时间标记
        boundaries = []
        for i, seg in enumerate(segments):
            start = seg['start']
            if i + 1 < len(segments):
                end = segments[i + 1]['start']
            else:
                end = duration
            boundaries.append((start, end))
    else:
        # 音频分析自动分配
        print("歌词无时间标记，进行音频分析...")
        wav_path = job_dir / "audio_raw.wav"
        extract_audio(video_path, ffmpeg, wav_path)
        energies = analyze_audio_energy(wav_path)
        
        intro_end = args.intro_end if args.intro_end else None
        if intro_end is None:
            # 自动检测前奏结束点
            avg_e = sum(energies) / len(energies)
            threshold = avg_e * 0.15
            for i, e in enumerate(energies):
                if e > threshold and i * 0.1 > 5:  # 至少5秒前奏
                    intro_end = i * 0.1
                    break
            if intro_end is None:
                intro_end = 8.0
        
        print(f"前奏结束: {intro_end:.1f}s")
        
        boundaries = find_vocal_segment_boundaries(
            energies, len(segments), duration, intro_end
        )
    
    # 打印时间轴
    print("\n时间轴:")
    for i, (seg, (start, end)) in enumerate(zip(segments, boundaries), 1):
        print(f"  [{i}] {format_srt_time(start)} --> {format_srt_time(end)} | {seg['text'][:40]}...")
    
    # 生成 SRT
    srt_path = job_dir / "subtitles" / "source.original.srt"
    srt_path.parent.mkdir(parents=True, exist_ok=True)
    generate_srt(segments, boundaries, srt_path)
    print(f"\nSRT 已生成: {srt_path}")
    
    # 读取翻译
    if args.translations:
        trans_lines = args.translations.read_text(encoding='utf-8').strip().split('\n')
        translations = [line.strip() for line in trans_lines]
    else:
        # 交互式翻译或由 AI 翻译
        print("\n请提供翻译（每段一行，输入空行结束）:")
        translations = []
        for i, seg in enumerate(segments, 1):
            print(f"\n[{i}] {seg['text']}")
            trans = input("  翻译: ").strip()
            translations.append(trans)
    
    if len(translations) != len(segments):
        print(f"错误: {len(segments)} 段歌词但只有 {len(translations)} 条翻译")
        return 1
    
    # 运行 JZSub 流水线
    output = run_jzsub_pipeline(
        video_path=video_path,
        srt_path=srt_path,
        job_dir=job_dir,
        source_lang=args.source_lang,
        target_lang=args.target_lang,
        translations=translations,
        ffmpeg=ffmpeg,
        ffprobe=ffprobe,
        burn_preset=args.preset,
        burn_crf=args.crf,
        allow_missing_font=args.allow_missing_font,
    )
    
    print(f"\n✓ 完成！双语字幕版视频: {output}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
