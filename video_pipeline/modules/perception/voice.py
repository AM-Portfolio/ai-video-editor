import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import torch
import torchaudio
import os
import shutil
# Add project root to sys.path for modular imports
sys.path.append(os.getcwd())

from core import config as cfg_loader
config = cfg_loader.load_config()
BASE_DIR = "processing"

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

from core.logging import DecisionLog
from core.scoring import ScoreKeeper
from core import state as state_manager

logger = DecisionLog()
scorer = ScoreKeeper()

def get_speech_score(video_path):
    """
    Calculate the ratio of speech to total duration.
    Returns score (0.0 - 1.0)
    """
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
        
        if not speech_timestamps:
            return 0.0
            
        # Calculate total speech samples
        total_speech_samples = sum([t['end'] - t['start'] for t in speech_timestamps])
        total_samples = waveform.size(1)
        
        if total_samples == 0:
            return 0.0
            
        return total_speech_samples / total_samples

    except Exception as e:
        print(f"   ⚠️ Error processing audio for {os.path.basename(video_path)}: {e}")
        return 0.0
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


import concurrent.futures

def process_file(args):
    path = args
    filename = os.path.basename(path)
    step_name = "🗣️  VAD (Voice) Scoring"
    
    if state_manager.is_step_done(filename, step_name):
        print(f"   ⏩ {filename} -> Resumed (Already Scored)")
        return

    if not os.path.exists(path):
        return

    try:
        speech_score = get_speech_score(path)
        
        # Persist Score
        scorer.update_score(filename, "vad_score", speech_score)
        
        # Log decision
        logger.log(
            module="vad_filter",
            decision="scored_clip",
            confidence=1.0, 
            reason="speech_analysis",
            metrics={
                "speech_ratio": round(speech_score, 2)
            }
        )
        
        print(f"   - {filename} -> Scored: {speech_score:.3f}")
        # Mark as done
        state_manager.mark_step_done(filename, step_name)
    except Exception as e:
        print(f"❌ Error processing {filename}: {e}")

if __name__ == "__main__":
    print(f"🎙️  Scanning {BASE_DIR} for human speech (VAD Scoring Mode)...")
    
    max_workers = max(1, os.cpu_count() - 2)
    files_found = False
    
    for clip in os.listdir(BASE_DIR):
        clip_dir = os.path.join(BASE_DIR, clip)
        if not os.path.isdir(clip_dir):
            continue

        if clip.startswith("output") or clip.startswith("temp"):
            continue

        print(f"   Processing clip folder: {clip}")

        tasks = []
        for file in os.listdir(clip_dir):
            if not file.endswith(".mp4"):
                continue

            src = os.path.join(clip_dir, file)
            tasks.append(src) # Only path
            
        if tasks:
            files_found = True
            with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
                executor.map(process_file, tasks)

    if not files_found:
        print("   ⚠️ No folders/clips found to score.")
