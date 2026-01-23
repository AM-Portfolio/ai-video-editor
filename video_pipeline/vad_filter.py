import torch
import torchaudio
import os
import shutil
import json

# Try to load config if available, though VAD model handles threshold mostly internally
# We can use a config value for min_speech_duration or similar if we wanted, 
# but for now we'll stick to the model's defaults or hardcoded logic as per plan.
try:
    with open("config.json") as f:
        config = json.load(f)
except FileNotFoundError:
    config = {}

BASE_DIR = "processing"

print("🧠 Loading Silero VAD Model...")
model, utils = torch.hub.load(
    repo_or_dir='snakers4/silero-vad',
    model='silero_vad',
    force_reload=False,
    trust_repo=True
)

(get_speech_timestamps, save_audio, read_audio, VADIterator, collect_chunks) = utils

import soundfile as sf
import subprocess
import tempfile
import torch

def has_speech(video_path):
    # Use ffmpeg to extract audio to a temp wav file
    # Then use soundfile to read it, bypassing torchaudio's flaky backend detection
    
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name
        
    try:
        # Extract audio: 16k sample rate, 1 channel (mono), pcm_s16le
        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-i", video_path,
            "-ar", "16000",
            "-ac", "1",
            "-c:a", "pcm_s16le",
            tmp_path
        ]
        subprocess.run(cmd, check=True)
        
        # Load the clean wav using soundfile
        data, sr = sf.read(tmp_path)
        # sr is guaranteed 16000 by ffmpeg
        
        # Convert to torch tensor (1, N)
        if data.ndim == 1:
            waveform = torch.from_numpy(data).float().unsqueeze(0)
        else:
            waveform = torch.from_numpy(data).float().T
            
        # get_speech_timestamps returns a list of distinct speech segments
        speech_timestamps = get_speech_timestamps(
            waveform, model, sampling_rate=16000
        )
        
        return len(speech_timestamps) > 0

    except Exception as e:
        print(f"   ⚠️ Error processing audio for {os.path.basename(video_path)}: {e}")
        return False
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


import concurrent.futures

def process_file(args):
    path, speech_dir, silent_dir = args
    filename = os.path.basename(path)
    
    if not os.path.exists(path):
        return

    try:
        is_speech = has_speech(path)
        target_dir = speech_dir if is_speech else silent_dir
        status = "🗣️ SPEECH" if is_speech else "🤫 SILENT"
        
        print(f"   - {filename} -> {status}", flush=True)
        shutil.move(path, os.path.join(target_dir, filename))
    except Exception as e:
        print(f"❌ Error processing {filename}: {e}")

if __name__ == "__main__":
    print(f"🎙️  Scanning {BASE_DIR} for human speech (VAD)...")
    
    max_workers = max(1, os.cpu_count() - 2)
    
    for clip in os.listdir(BASE_DIR):
        clip_dir = os.path.join(BASE_DIR, clip)
        if not os.path.isdir(clip_dir):
            continue

        keep_dir = os.path.join(clip_dir, "keep")
        if not os.path.isdir(keep_dir):
            continue

        speech_dir = os.path.join(keep_dir, "speech")
        silent_dir = os.path.join(keep_dir, "silent")

        os.makedirs(speech_dir, exist_ok=True)
        os.makedirs(silent_dir, exist_ok=True)

        print(f"   Processing clip folder: {clip}")

        tasks = []
        for file in os.listdir(keep_dir):
            if not file.endswith(".mp4"):
                continue

            src = os.path.join(keep_dir, file)
            # Only add if it exists (race check)
            if os.path.exists(src):
                tasks.append((src, speech_dir, silent_dir))
        
        if tasks:
            print(f"   🚀 Starting {len(tasks)} parallel tasks...")
            with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
                executor.map(process_file, tasks)
        else:
            print("   ⚠️ No tasks for this clip.")

