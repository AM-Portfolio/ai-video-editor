import json
import os
import requests

import sys
# Add project root to sys.path for modular imports
sys.path.append(os.getcwd())

from core import config as cfg_loader
from core import path_utils

class RegexOptimizer:
    def __init__(self, config_path=None, keywords_path="data/keywords_active.json"):
        self.config = cfg_loader.load_config(config_path)
        self.keywords_path = keywords_path
        proc_dir = path_utils.get_processing_dir()
        self.log_path = os.path.join(proc_dir, "auto_learning_log.json")
        self.tags_path = os.path.join(proc_dir, "semantic_tags.json")

    def is_safe_to_automate(self, keyword, category, transcript):
        """Use LLM to vet if a keyword is specific enough to be used without review."""
        semantic_cfg = self.config.get("semantic_model", {})
        api_key = semantic_cfg.get("api_key")
        model = semantic_cfg.get("model", "ServiceNow-AI/Apriel-1.6-15b-Thinker")
        
        if not api_key: return False

        prompt = f"""Evaluate this keyword/phrase for use in a high-speed Regex filter.
Keyword: "{keyword}"
Category: "{category}"
Original Context: "{transcript}"

Questions:
1. Is this word too generic (e.g. 'the', 'is', 'code')?
2. If we always label clips containing this word as '{category}', will we have many false positives?

Answer ONLY with 'SAFE' if it is highly specific and technical, or 'RISKY' if it might match random conversation."""
        
        from together import Together
        client = Together(api_key=api_key)
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}]
            )
            return "SAFE" in response.choices[0].message.content.upper()
        except: return False

    def optimize(self):
        print("🤖 AI-Supervised Knowledge Distillation (Autonomous Mode)...")
        
        if not self.config.get("self_learning", True):
            print("🛑 Sub-system disabled.")
            return
            
        if not os.path.exists(self.tags_path):
            print("⚠️ No tags found.")
            return

        with open(self.tags_path) as f: tags = json.load(f)

        llm_learned_clips = [
            (k, v) for k, v in tags.items() 
            if v.get("attribution") == "llm" and v.get("category") != "general"
        ]
        
        if not llm_learned_clips:
            print("✅ Fast-path optimally covers this run.")
            return

        # Distill from top 5 clips
        llm_learned_clips = llm_learned_clips[:5] 
        with open(self.keywords_path) as f: active = json.load(f)

        new_count = 0
        updates = []

        from together import Together
        client = Together(api_key=self.config.get("semantic_model", {}).get("api_key"))

        for clip_id, clip_data in llm_learned_clips:
            cat = clip_data.get("category")
            text = clip_data.get("transcript")
            
            print(f"   🤔 Analyzing clip {clip_id} for new keywords...", end="\r")

            # 1. Propose
            prompt = f"Identify the most specific 1 or 2 word technical phrase in this: '{text}'. Return ONLY the phrase."
            try:
                res = client.chat.completions.create(model="ServiceNow-AI/Apriel-1.6-15b-Thinker", messages=[{"role":"user","content":prompt}])
                kw = res.choices[0].message.content.strip().lower().replace('"', '').replace("'", "")
                
                if kw and kw not in active.get(cat, []):
                    # 2. AI Vetting
                    if self.is_safe_to_automate(kw, cat, text):
                        active[cat].append(kw)
                        updates.append({"keyword": kw, "category": cat, "source": clip_id})
                        new_count += 1
                        print(f"   ✨ Auto-Learning: +'{kw}' -> {cat} (Vetted Safe)")
            except: pass

        if new_count > 0:
            with open(self.keywords_path, "w") as f:
                json.dump(active, f, indent=4)
            # Log for the user
            with open(self.log_path, "w") as f:
                json.dump(updates, f, indent=4)
            print(f"✅ Autonomous Update: Added {new_count} new vetted heuristics.")
        else:
            print("✅ No high-confidence heuristics found to automate.")

if __name__ == "__main__":
    optimizer = RegexOptimizer()
    optimizer.optimize()
