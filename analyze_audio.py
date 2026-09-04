"""Analyze audio to detect vocal segments and silence for subtitle timing."""
import wave
import struct
import json
import os

WAV_PATH = os.path.join(os.path.dirname(__file__), "jzsub-jobs/irn5wUFJe_8/audio_raw.wav")

def analyze_audio():
    with wave.open(WAV_PATH, 'rb') as wav:
        n_frames = wav.getnframes()
        sample_rate = wav.getframerate()
        n_channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        
        print(f"Channels: {n_channels}, Sample rate: {sample_rate}, Frames: {n_frames}")
        print(f"Duration: {n_frames / sample_rate:.1f}s")
        
        # Read all frames
        raw = wav.readframes(n_frames)
    
    # Parse as 16-bit signed integers
    samples = struct.unpack(f'<{n_frames}h', raw)
    
    # Analyze energy in 100ms windows
    window_size = int(sample_rate * 0.1)  # 100ms
    n_windows = len(samples) // window_size
    
    energies = []
    for i in range(n_windows):
        chunk = samples[i * window_size : (i + 1) * window_size]
        # RMS energy
        sum_sq = sum(s * s for s in chunk)
        rms = (sum_sq / len(chunk)) ** 0.5
        energies.append(rms)
    
    # Find threshold (average of all energies * 0.3 as silence threshold)
    avg_energy = sum(energies) / len(energies)
    threshold = avg_energy * 0.15
    
    print(f"\nAverage energy: {avg_energy:.0f}")
    print(f"Silence threshold: {threshold:.0f}")
    
    # Detect silence regions (energy below threshold)
    # Group consecutive silent/active windows
    segments = []
    current_active = energies[0] > threshold
    seg_start = 0
    
    for i in range(1, n_windows):
        is_active = energies[i] > threshold
        if is_active != current_active:
            seg_end = i
            seg_duration = (seg_end - seg_start) * 0.1
            seg_time_start = seg_start * 0.1
            seg_time_end = seg_end * 0.1
            avg_e = sum(energies[seg_start:seg_end]) / max(1, seg_end - seg_start)
            segments.append({
                'active': current_active,
                'start': seg_time_start,
                'end': seg_time_end,
                'duration': seg_duration,
                'avg_energy': avg_e
            })
            current_active = is_active
            seg_start = i
    
    # Last segment
    seg_end = n_windows
    seg_duration = (seg_end - seg_start) * 0.1
    seg_time_start = seg_start * 0.1
    seg_time_end = n_windows * 0.1
    avg_e = sum(energies[seg_start:seg_end]) / max(1, seg_end - seg_start)
    segments.append({
        'active': current_active,
        'start': seg_time_start,
        'end': seg_time_end,
        'duration': seg_duration,
        'avg_energy': avg_e
    })
    
    # Print silence segments (gaps between vocal lines)
    print("\n=== Silence segments (potential gaps between lyrics) ===")
    for seg in segments:
        if not seg['active'] and seg['duration'] > 0.3:
            print(f"  Silence: {seg['start']:.1f}s - {seg['end']:.1f}s ({seg['duration']:.1f}s)")
    
    # Print active segments (vocal/instrumental)
    print("\n=== Active segments ===")
    for seg in segments:
        if seg['active'] and seg['duration'] > 0.5:
            print(f"  Active: {seg['start']:.1f}s - {seg['end']:.1f}s ({seg['duration']:.1f}s) energy={seg['avg_energy']:.0f}")
    
    # Also print energy profile in 1-second buckets
    print("\n=== Energy profile (1s buckets) ===")
    bucket_size = 10  # 10 * 100ms = 1s
    for i in range(0, n_windows, bucket_size):
        end = min(i + bucket_size, n_windows)
        bucket_avg = sum(energies[i:end]) / (end - i)
        bar = '#' * int(bucket_avg / 100)
        timestamp = i * 0.1
        print(f"  {timestamp:6.1f}s [{bar:40s}] {bucket_avg:.0f}")
    
    # Output segment data as JSON for further processing
    output = {
        'duration': n_windows * 0.1,
        'segments': segments,
        'energies_1s': [sum(energies[i:i+bucket_size])/bucket_size for i in range(0, n_windows, bucket_size)]
    }
    
    out_path = os.path.join(os.path.dirname(__file__), "jzsub-jobs/irn5wUFJe_8/audio_analysis.json")
    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"\nAnalysis saved to: {out_path}")

if __name__ == '__main__':
    analyze_audio()
