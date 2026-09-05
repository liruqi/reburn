#!/usr/bin/env python3
"""Run faster-whisper on the audio file to get word-level and segment-level timestamps."""

import json
import sys
import os

audio_path = "/Users/nicolasmac/Documents/GitHub/reburn/ytb/irn5wUFJe_8/audio_16k.wav"
output_path = "/Users/nicolasmac/Documents/GitHub/reburn/ytb/irn5wUFJe_8/whisper_output.json"

from faster_whisper import WhisperModel

print("Loading model (large-v3)...", flush=True)
model = WhisperModel("large-v3", device="cpu", compute_type="int8")

print(f"Transcribing {audio_path}...", flush=True)
segments, info = model.transcribe(
    audio_path,
    language="th",
    task="transcribe",
    word_timestamps=True,
    vad_filter=True,
    beam_size=5,
)

result = {
    "language": info.language,
    "language_probability": info.language_probability,
    "duration": info.duration,
    "segments": [],
    "words": []
}

for segment in segments:
    seg = {
        "start": segment.start,
        "end": segment.end,
        "text": segment.text.strip(),
        "words": []
    }
    if segment.words:
        for word in segment.words:
            w = {
                "start": word.start,
                "end": word.end,
                "word": word.word.strip(),
                "probability": word.probability
            }
            seg["words"].append(w)
            result["words"].append(w)
    result["segments"].append(seg)
    print(f"  [{segment.start:.2f} -> {segment.end:.2f}] {segment.text.strip()}", flush=True)

with open(output_path, "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print(f"\nDone! Output saved to {output_path}", flush=True)
print(f"Total segments: {len(result['segments'])}", flush=True)
print(f"Total words: {len(result['words'])}", flush=True)
