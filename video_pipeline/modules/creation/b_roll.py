import json
import sys
import os
sys.path.append(os.getcwd()) # FIX: Allow importing 'core' module
import time
import requests
import base64
from core import config as cfg_loader
from core import path_utils

class BRollGenerator:
    def __init__(self, config_path=None):
        self.config = cfg_loader.load_config(config_path)
        self.proc_dir = path_utils.get_processing_dir()
        self.b_roll_dir = os.path.join(self.proc_dir, "b_roll")
        os.makedirs(self.b_roll_dir, exist_ok=True)
        
        self.tags_path = os.path.join(self.proc_dir, "semantic_tags.json")
        self.schedule_path = os.path.join(self.b_roll_dir, "b_roll_schedule.json")
        
        # Pacing Settings (The Editorial Logic)
        self.min_score = 4          # Lowered from 7 to 4 to ensure B-roll triggers
        self.min_gap_sec = 15       # Cooldown between images
        self.max_per_min = 3        # Visual Budget
        
        # Model Settings (FLUX.2-max)
        self.api_key = self.config.get("semantic_model", {}).get("api_key") or os.getenv("TOGETHER_API_KEY")
        self.model = "Rundiffusion/Juggernaut-Lightning-Flux"

    def select_moments(self):
        """
        Applies Editorial Logic: Score filtering + Cooldowns + Budget.
        Returns a list of scheduled visuals: [{ "clip_id": "...", "prompt": "...", "timestamp": 12.5 }]
        """
        if not os.path.exists(self.tags_path):
            print("❌ No semantic tags found.")
            return []
            
        with open(self.tags_path) as f:
            tags = json.load(f)
            
        # 1. Candidate Selection (Score Filter)
        candidates = []
        for clip_id, data in tags.items():
            score = data.get("visual_score", 0)
            if score >= self.min_score:
                candidates.append({
                    "clip_id": clip_id,
                    "score": score,
                    "prompt": data.get("visual_description", ""),
                    # We need real timestamps. For now, assuming clip_id sort order ~ time.
                    # In a real app, we'd map clip_id to global time. 
                    # Let's assume sequential order for cooldown logic.
                    "index": 0 
                })
        
        # Sort by filename (approximate temporal order)
        candidates.sort(key=lambda x: x["clip_id"])
        
        # 2. Editorial Pacing (Cooldown)
        schedule = []
        last_index = -999
        
        print(f"   🎥 Found {len(candidates)} high-potential visual moments.")
        
        # Simple Logic: Clip-based cooldown (since we don't have global seconds easily without map)
        # Using "Clip Count" as proxy for time. 1 clip ~= 5-10 seconds.
        # So 15s gap ~= 2-3 clips gap.
        CLIP_GAP = 3 
        
        filtered = []
        for i, cand in enumerate(candidates):
            # Find the "clip index" from filename? 
            # heuristic: chunk_0005.mp4 -> 5
            try:
                curr_idx = int(cand["clip_id"].split('_')[-1].split('.')[0])
            except: curr_idx = i
            
            cand["index"] = curr_idx
            
            if curr_idx - last_index >= CLIP_GAP:
                filtered.append(cand)
                last_index = curr_idx
            else:
                # Collision! Pick the higher score?
                # The previous one is already added. Check if current is better?
                # Simple First-Come logic is safer for narrative flow, 
                # unless current is MUCH better. 
                pass
                
        print(f"   ✂️  Pacing Filter: Reduced to {len(filtered)} visuals (Cooldown Rules applied).")
        return filtered

    def generate_image(self, prompt, output_path):
        """Generates 16:9 B-Roll using FLUX.2-max"""
        if os.path.exists(output_path):
            return True # caching
            
        # SAFETY CHECK: Verify we can write to disk BEFORE calling API $$
        d = os.path.dirname(output_path)
        if not os.path.exists(d):
            try:
                os.makedirs(d, exist_ok=True)
            except OSError as e:
                print(f"      ❌ SAFETY ABORT: Cannot create directory {d}: {e}")
                return False

        print(f"      🎨 Generating: \"{prompt[:40]}...\"")
        
        url = "https://api.together.xyz/v1/images/generations"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # Refine prompt for B-Roll style
        full_prompt = f"Cinematic B-Roll shot, 16:9, highly detailed, photorealistic. {prompt}"
        
        payload = {
            "model": self.model,
            "prompt": full_prompt,
            "negative_prompt": "text, watermark, ugly, distorted, cartoon, anime",
            "response_format": "b64_json",
            "disable_safety_checker": True,
            "width": 1024, # Juggernaut requires mod 64
            "height": 576,
            "steps": 4 # Juggernaut Lightning is fast
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers)
            if response.status_code == 200:
                data = response.json()
                b64 = data["data"][0]["b64_json"]
                with open(output_path, "wb") as f:
                     f.write(base64.b64decode(b64))
                return True
            else:
                err_msg = response.text
                print(f"      ❌ API Error: {err_msg}")
                
                # RETRY LOGIC: If NSFW or Safety error, use Safe Fallback
                # Check for various safety flags in response text
                if "NSFW" in err_msg or "safety" in err_msg or "content" in err_msg:
                    if "fallback" not in prompt.lower(): # Prevent infinite recursion
                        print("      🛡️ Safety Triggered. Retrying with SAFE FALLBACK prompt...")
                        safe_prompt = "Abstract cinematic lighting, soft focus, professional corporate atmosphere, 4k, aesthetics"
                        return self.generate_image(safe_prompt + " fallback", output_path)
                    
        except Exception as e:
            print(f"      ❌ Gen Failed: {e}")
        return False

    def run(self):
        print("🎞️  Running B-Roll Generator (Smart Pacing)...")
        if not self.api_key:
            print("❌ No API Key found.")
            return

        schedule = self.select_moments()
        
        # Generate Limit (Visual Budget PER RUN to save money while testing)
        # Process top N for now? Or all? 
        # Let's process all selected by the filter.
        
        final_schedule = {}
        
        for item in schedule:
            # Flatten path: 2024-01-01/chunk_01.mp4 -> broll_2024-01-01_chunk_01.mp4.png
            safe_id = item['clip_id'].replace('/', '_').replace('\\', '_')
            filename = f"broll_{safe_id}.png"
            path = os.path.join(self.b_roll_dir, filename)
            
            success = self.generate_image(item["prompt"], path)
            if success:
                final_schedule[item["clip_id"]] = {
                    "image_path": path,
                    "prompt": item["prompt"]
                }
                
        # Save Schedule for Editor
        with open(self.schedule_path, "w") as f:
            json.dump(final_schedule, f, indent=2)
            
        print(f"✅ B-Roll Generation Complete. {len(final_schedule)} images ready.")

if __name__ == "__main__":
    gen = BRollGenerator()
    gen.run()
