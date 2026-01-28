
import json
import sys
import os
sys.path.append(os.getcwd()) # FIX: Allow importing 'core' module
from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip, concatenate_videoclips
from core import config as cfg_loader
from core import path_utils

class SmartEditor:
    def __init__(self, config_path=None):
        self.config = cfg_loader.load_config(config_path)
        self.proc_dir = path_utils.get_processing_dir()
        self.output_dir = path_utils.get_output_videos_dir()
        self.b_roll_dir = os.path.join(self.proc_dir, "b_roll")
        self.schedule_path = os.path.join(self.b_roll_dir, "b_roll_schedule.json")
        
    def run(self):
        print("🎬 Runnning Smart Editor (MoviePy Assembly)...")
        
        # 1. Gather Clips (Recursive Scan for Subdirectories)
        # Fix: splitter.py creates subfolders (processing/am/video_name/chunk_00.mp4)
        # We need to find all chunks.
        
        clip_paths = []
        for root, dirs, files in os.walk(self.proc_dir):
            for f in files:
                if f.endswith(".mp4") and f.startswith("chunk_"):
                    # This is a chunk!
                    full_path = os.path.join(root, f)
                    # Rel path for key matching: 'video_name/chunk_00.mp4'
                    rel_path = os.path.relpath(full_path, self.proc_dir)
                    clip_paths.append((rel_path, full_path))
        
        # Sort by filename (temporal order usually holds: chunk_0000, chunk_0001)
        # We should sort by the full path or just the chunk number if possible
        clip_paths.sort(key=lambda x: x[0])
        
        if not clip_paths:
            print("❌ No chunk clips found in subdirectories.")
            return

        print(f"   🎞️  Found {len(clip_paths)} clips to merge.")
        
        # 3. Batch Processing Logic to Avoid OOM
        # Instead of 1 giant Composite, we process in chunks of N clips, render them, then concat.
        BATCH_SIZE = 20
        temp_parts_dir = os.path.join(self.proc_dir, "temp_parts")
        os.makedirs(temp_parts_dir, exist_ok=True)
        
        # Load Schedule once
        schedule = {}
        if os.path.exists(self.schedule_path):
            with open(self.schedule_path) as f: schedule = json.load(f)

        part_files = []
        
        # Split clip_paths into batches
        for i in range(0, len(clip_paths), BATCH_SIZE):
            batch_idx = i // BATCH_SIZE
            batch_clips_meta = clip_paths[i : i + BATCH_SIZE]
            
            print(f"   🧱 Processing Batch {batch_idx+1} ({len(batch_clips_meta)} clips)...")
            
            batch_timeline = []
            batch_start_time = 0.0 # Relative to this batch
            
            # We need to know the GLOBAL start time of this batch to match B-Roll correctly
            # Check clip_start_times relative to global
            # But we haven't calculated global times yet for items *ahead* of us in strict loop...
            # Actually we did in the previous heuristic loop? 
            # Re-calculate on the fly:
            # We must know the duration of previous batches.
            # Ideally, simple concatenation:
            
            # Construct Batch
            batch_video_clips = []
            
            for rel_path, full_path in batch_clips_meta:
                 try:
                     c = VideoFileClip(full_path)
                     batch_video_clips.append(c)
                 except: pass
                 
            if not batch_video_clips: continue
            
            # Create Main Track for Batch
            batch_main = concatenate_videoclips(batch_video_clips, method="compose")
            
            # Find B-Roll overlays for this specific set of clips?
            # MAPPING DIFFICULTY: We need to know the time offsets within this batch.
            # AND we need to know which clips are in this batch to look up the schedule.
            
            batch_layers = []
            current_batch_time = 0.0
            
            for idx, (rel_path, full_path) in enumerate(batch_clips_meta):
                # How long is this clip? We need to look it up in batch_video_clips[idx]
                # But we might have skipped some if error? logic above matches index if no err.
                if idx < len(batch_video_clips):
                    clip_dur = batch_video_clips[idx].duration
                    
                    # Do we have b-roll for 'rel_path'?
                    if rel_path in schedule:
                        data = schedule[rel_path]
                        img_path = data["image_path"]
                        if os.path.exists(img_path):
                            # Overlay relative to BATCH start
                            # Duration: 3s
                            b_clip = (ImageClip(img_path)
                                     .set_start(current_batch_time)
                                     .set_duration(min(3.0, clip_dur)) # Don't exceed clip
                                     .set_position("center")
                                     .resize(height=batch_main.h)
                                     .crossfadein(0.5)
                                     .crossfadeout(0.5))
                            batch_layers.append(b_clip)
                    
                    current_batch_time += clip_dur

            # Composite Batch
            final_batch = CompositeVideoClip([batch_main] + batch_layers)
            
            part_path = os.path.join(temp_parts_dir, f"part_{batch_idx:03d}.mp4")
            
            # Render Batch
            try:
                final_batch.write_videofile(part_path, fps=24, codec="libx264", audio_codec="aac", threads=4, preset="fast", logger=None)
                part_files.append(part_path)
            except Exception as e:
                print(f"❌ Failed batch {batch_idx}: {e}")
            finally:
                # Cleanup Batch
                final_batch.close()
                for c in batch_video_clips: c.close()
                for b in batch_layers: b.close()
                
        # 4. Final Concatenation of Parts using FFmpeg (via MoviePy or Subprocess)
        if part_files:
            print(f"   🔗 Concatenating {len(part_files)} parts...")
            output_path = os.path.join(self.output_dir, "final_video_smart.mp4")
            
            # Create text file for ffmpeg concat
            list_path = os.path.join(temp_parts_dir, "concat_list.txt")
            with open(list_path, "w") as f:
                for p in part_files:
                    f.write(f"file '{p}'\n")
            
            # Run ffmpeg concat command
            # ffmpeg -f concat -safe 0 -i list.txt -c copy output.mp4
            cmd = [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", list_path, "-c", "copy", output_path
            ]
            try:
                import subprocess
                subprocess.run(cmd, check=True)
                print(f"   💾 Saved to {output_path}")
                print("✅ Editing Complete.")
            except Exception as e:
                print(f"❌ Final Concat failed: {e}")
        else:
            print("❌ No parts generated.")

if __name__ == "__main__":
    editor = SmartEditor()
    editor.run()
