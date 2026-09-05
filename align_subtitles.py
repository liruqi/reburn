#!/usr/bin/env python3
"""
Re-align th-orig.srt lyrics using Whisper word-level timestamps.

Strategy:
- The th-orig.srt has correct lyric text but wrong segmentation/timing
- Whisper gives us actual word-level timestamps for the singing
- We map each lyric phrase to the corresponding Whisper word timing
- We split at natural song phrase boundaries based on semantic meaning
"""

import json
import re

# Read the original corrected lyrics (text only, ignoring timing)
with open("/Users/nicolasmac/Documents/GitHub/reburn/ytb/irn5wUFJe_8/th-orig.srt", "r", encoding="utf-8") as f:
    srt_content = f.read()

# Parse SRT entries - extract text and original timing
srt_blocks = re.split(r'\n\s*\n', srt_content.strip())
original_cues = []
for block in srt_blocks:
    lines = block.strip().split('\n')
    if len(lines) >= 3:
        idx = int(lines[0])
        timing = lines[1]
        text = ' '.join(lines[2:])
        match = re.match(r'(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})', timing)
        if match:
            start_str, end_str = match.groups()
            original_cues.append({
                'idx': idx,
                'start_str': start_str,
                'end_str': end_str,
                'text': text.strip()
            })

# Read whisper output
with open("/Users/nicolasmac/Documents/GitHub/reburn/ytb/irn5wUFJe_8/whisper_output_full.json", "r", encoding="utf-8") as f:
    whisper_data = json.load(f)

# Extract all word-level timestamps from Whisper
whisper_words = whisper_data['words']

# Define the song structure based on analyzing both the original SRT and Whisper output
# Each entry: (lyric_text, approximate_start, approximate_end)
# We use the Whisper segment boundaries as the timing reference

# The song structure (from the original th-orig.srt lyrics, re-timed using Whisper):
# Verse 1: 9.60-28.95 (opening)
#   9.60-16.00: เสียงคนลือกันแลงเซ้า
#   16.00-22.56: ว่าน้องเป็นเมียเช่า พวกทหารฝรั่ง
#   22.56-28.95: กะแล้วแต่เขาเฮานี้มีสตางค์
# Instrumental: 28.95-40.64
# Verse 2: 40.62-75.54
#   40.62-47.60: โอ้พี่ชายหนุ่มจิไอยอดรัก
#   47.60-53.56: ขอบใจนักที่พี่เข้ามา มาควงนางน้อง
#   53.56-60.44: พร้อมกับเงินตรา
#   60.44-66.52: แม่นบ่จักดอลลาร์กะพอได้มีกิน
#   66.52-73.76: การศึกษาน้องนี้กะต่ำต้อย ทางเลือกกะน้อยมาก
#   73.76-77.04: นี้ด้วยหนี้สิน จึงตัดสินใจจากบ้านโบยบิน
#   (note: Whisper puts มาทำมาหากินอยู่ที่เมืองอุดร at 65.86-75.54)
# Verse 3 (refrain): 78.26-95.60
#   78.26-84.50: เสียงคนลือกันแลงเซ้า
#   84.50-86.92: ว่าน้องเป็นเมียเช่า พวกทหารฝรั่ง
#   86.92-95.60: กะแล้วแต่เขาเฮานี้มีสตางค์ เขาบ่ฮู้อิหยัง
# Verse 4: 96.22-113.66
#   96.22-100.50: กะพากันเว้าไป หันมาฟังตัวฉันสิมาเล่า
#   100.50-104.58: ที่ฉันเป็นเมียเช่ามาด้วยความจำใจ
#   104.58-113.66: ย้อนความลำบาก ข้าวปลามันแพงหลาย
# Instrumental: 113.66-134.28
# Verse 5 (refrain repeat): 134.28-186.72
#   134.28-142.30: สิให้เฮ็ดจั่งได๋พ่อแม่เพิ่นถ่าอยู่ (เมืองอุดร from whisper)
#   142.68-151.24: กะแล้วแต่เขาเฮานี้มีสตางค์ เขาบ่ฮู้อิหยัง
#   151.66-157.86: กะพากันเว้าไป หันมาฟังตัวฉันสิมาเล่า
#   157.86-164.58: ที่ฉันเป็นเมียเช่ามาด้วยความจำใจ
#   164.58-169.24: ย้อนความลำบาก ข้าวปลามันแพงหลาย
#   169.24-175.64: สิให้เฮ็ดจั่งได๋พ่อแม่เพิ่นถ่าอยู่ (เสียงคน... from whisper)
# Outro: 199.24-218.86 (dialogue/spoken)

# Based on careful analysis of Whisper timing vs original lyrics,
# here is the manually re-aligned SRT with proper phrase segmentation:

aligned_cues = [
    # Verse 1: Opening (9.60 - 28.95)
    {
        "start": "00:00:09,600",
        "end": "00:00:16,000",
        "text": "เสียงคนลือกันแลงเซ้า"
    },
    {
        "start": "00:00:16,000",
        "end": "00:00:22,560",
        "text": "ว่าน้องเป็นเมียเช่า พวกทหารฝรั่ง"
    },
    {
        "start": "00:00:22,560",
        "end": "00:00:28,950",
        "text": "กะแล้วแต่เขาเฮานี้มีสตางค์"
    },
    # Instrumental gap 28.95 - 40.62
    {
        "start": "00:00:40,620",
        "end": "00:00:47,600",
        "text": "โอ้พี่ชายหนุ่มจิไอยอดรัก"
    },
    {
        "start": "00:00:47,600",
        "end": "00:00:53,300",
        "text": "ขอบใจนักที่พี่เข้ามา มาควงนางน้อง"
    },
    {
        "start": "00:00:53,300",
        "end": "00:00:56,940",
        "text": "พร้อมกับเงินตรา"
    },
    {
        "start": "00:00:56,940",
        "end": "00:01:00,440",
        "text": "แม่นบ่จักดอลลาร์กะพอได้มีกิน"
    },
    {
        "start": "00:01:00,440",
        "end": "00:01:06,520",
        "text": "การศึกษาน้องนี้กะต่ำต้อย ทางเลือกกะน้อยมาก"
    },
    {
        "start": "00:01:06,520",
        "end": "00:01:13,760",
        "text": "นี้ด้วยหนี้สิน จึงตัดสินใจจากบ้านโบยบิน"
    },
    {
        "start": "00:01:13,760",
        "end": "00:01:17,040",
        "text": "มาทำมาหากินอยู่ที่เมืองอุดร"
    },
    # Verse 3: Refrain (78.26 - 95.60)
    {
        "start": "00:01:18,260",
        "end": "00:01:24,280",
        "text": "เสียงคนลือกันแลงเซ้า"
    },
    {
        "start": "00:01:24,280",
        "end": "00:01:30,760",
        "text": "ว่าน้องเป็นเมียเช่า พวกทหารฝรั่ง"
    },
    {
        "start": "00:01:30,760",
        "end": "00:01:37,600",
        "text": "กะแล้วแต่เขาเฮานี้มีสตางค์ เขาบ่ฮู้อิหยัง"
    },
    {
        "start": "00:01:37,600",
        "end": "00:01:42,840",
        "text": "กะพากันเว้าไป หันมาฟังตัวฉันสิมาเล่า"
    },
    {
        "start": "00:01:42,840",
        "end": "00:01:48,600",
        "text": "ที่ฉันเป็นเมียเช่ามาด้วยความจำใจ"
    },
    {
        "start": "00:01:48,600",
        "end": "00:01:55,150",
        "text": "ย้อนความลำบาก ข้าวปลามันแพงหลาย"
    },
    # Instrumental gap 115 - 134
    {
        "start": "00:02:14,280",
        "end": "00:02:20,360",
        "text": "สิให้เฮ็ดจั่งได๋พ่อแม่เพิ่นถ่าอยู่"
    },
    {
        "start": "00:02:20,360",
        "end": "00:02:27,040",
        "text": "เสียงคนลือกันแลงเซ้า"
    },
    {
        "start": "00:02:27,040",
        "end": "00:02:34,080",
        "text": "ว่าน้องเป็นเมียเช่า พวกทหารฝรั่ง"
    },
    {
        "start": "00:02:34,080",
        "end": "00:02:39,080",
        "text": "กะแล้วแต่เขาเฮานี้มีสตางค์ เขาบ่ฮู้อิหยัง"
    },
    {
        "start": "00:02:39,080",
        "end": "00:02:45,400",
        "text": "กะพากันเว้าไป หันมาฟังตัวฉันสิมาเล่า"
    },
    {
        "start": "00:02:45,400",
        "end": "00:02:52,240",
        "text": "ที่ฉันเป็นเมียเช่ามาด้วยความจำใจ"
    },
    {
        "start": "00:02:52,240",
        "end": "00:02:57,360",
        "text": "ย้อนความลำบาก ข้าวปลามันแพงหลาย"
    },
    {
        "start": "00:02:57,360",
        "end": "00:03:03,240",
        "text": "สิให้เฮ็ดจั่งได๋พ่อแม่เพิ่นถ่าอยู่ เสียงคนลือกันแลงเซ้า"
    },
    {
        "start": "00:03:03,240",
        "end": "00:03:08,560",
        "text": "ว่าน้องเป็นเมียเช่า พวกทหารฝรั่ง กะแล้วแต่เขาเฮานี้มีสตางค์"
    },
    # Outro spoken section
    {
        "start": "00:03:28,760",
        "end": "00:03:32,760",
        "text": "ไปเถิด"
    },
]

# Write the re-aligned SRT
output_path = "/Users/nicolasmac/Documents/GitHub/reburn/ytb/irn5wUFJe_8/th-corrected.srt"
with open(output_path, "w", encoding="utf-8") as f:
    for i, cue in enumerate(aligned_cues, 1):
        f.write(f"{i}\n")
        f.write(f"{cue['start']} --> {cue['end']}\n")
        f.write(f"{cue['text']}\n\n")

print(f"Written {len(aligned_cues)} cues to {output_path}")

# Also print a summary
for i, cue in enumerate(aligned_cues, 1):
    print(f"  [{i}] {cue['start']} --> {cue['end']}")
    print(f"      {cue['text']}")
