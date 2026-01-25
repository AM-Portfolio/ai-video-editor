import json
import os
import shutil
import warnings
import sys
# Add project root to sys.path for modular imports
sys.path.append(os.getcwd())

import core.state as state_manager
from core import config as cfg_loader

# Suppress FP16 warning if CPU
warnings.filterwarnings("ignore")

try:
    import whisper
    import torch
    import requests
except ImportError:
    print("❌ Missing dependencies. Please run: pip install -r video_pipeline/requirements.txt")
    sys.exit(1)

class SemanticTagger:
    def __init__(self, config_path=None):
        self.config = cfg_loader.load_config(config_path)
        self.scores_path = "processing/scores.json"
        self.output_path = "processing/semantic_tags.json"
        self.keywords_path = "data/keywords_active.json"
        self.keywords = self._load_keywords()
        
        # Configuration for "Pre-Filtering"
        # We only transcribe clips that are "kinda good" to save time.
        self.min_quality_threshold = 0.4 # Lower than final keep threshold to be safe
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = None # Lazy load

    def _load_keywords(self):
        try:
            with open(self.keywords_path) as f:
                return json.load(f)
        except Exception:
            return {"product_related": [], "funny": []}

    def load_model(self):
        if self.model is None:
            print(f"🧠 Loading Whisper model (small) on {self.device}...")
            try:
                self.model = whisper.load_model("small", device=self.device)
            except Exception as e:
                print(f"❌ Failed to load Whisper: {e}")
                return False
        return True

    def get_quality_score(self, metrics):
        # Rough estimate using default weights if not in config
        decider_cfg = self.config.get("decider", {})
        weights = decider_cfg.get("weights", {"face": 0.4, "motion": 0.3, "speech": 0.3})
        
        score = (
            metrics.get("face_score", 0.0) * weights.get("face", 0) +
            metrics.get("motion_score", 0.0) * weights.get("motion", 0) +
            metrics.get("vad_score", 0.0) * weights.get("speech", 0)
        )
        return score

    def transcribe(self, clip_path):
        if not self.model:
            return ""
        try:
            # Load transcription settings
            trans_cfg = self.config.get("transcription", {})
            lang = trans_cfg.get("language", "auto")
            prompt = trans_cfg.get("initial_prompt", "")
            
            # Whisper transcribes audio/video files directly
            # Passing language (if not 'auto') and initial_prompt for better context
            transcribe_args = {
                "fp16": (self.device == "cuda"),
                "initial_prompt": prompt
            }
            if lang and lang != "auto":
                transcribe_args["language"] = lang

            result = self.model.transcribe(clip_path, **transcribe_args)
            text = result.get("text", "").strip()
            return text
        except Exception as e:
            print(f"   ⚠️ Transcription failed for {os.path.basename(clip_path)}: {e}")
            return ""

    def classify_text(self, text, context_buffer=None):
        """
        Uses Regex/Keywords FIRST, then falls back to Together AI with Context.
        Categories: product_related, funny, general
        
        context_buffer: List of dicts [{"text": "...", "category": "..."}, ...] from previous chunks.
        """
        if not text or len(text) < 10:
            return "general", "too_short"

        # 1. Fast Regex/Keyword Check
        text_lower = text.lower()
        
        product_keywords = self.keywords.get("product_related", [])
        if any(w in text_lower for w in product_keywords):
            return "product_related", "regex"
            
        funny_keywords = self.keywords.get("funny", [])
        is_funny_regex = any(w in text_lower for w in funny_keywords)
        
        # If Regex says funny, but we have context, let's verify with LLM to avoid context-breaking.
        # e.g. "Hahaha" inside a DEEP technical convo should be product_related (or just kept with product flow).
        # We only skip to LLM if context is present OR if we want to be smart about laughter.
        
        # 2. Together AI / LLM (The Judge)
        semantic_cfg = self.config.get("semantic_model", {})
        provider = semantic_cfg.get("provider", "local")
        api_key = semantic_cfg.get("api_key")
        model = semantic_cfg.get("model", "ServiceNow-AI/Apriel-1.6-15b-Thinker")

        # Build Context String
        context_str = ""
        last_category = "general"
        if context_buffer:
            context_str = "PREVIOUS CONTEXT (History of conversation):\n"
            for item in context_buffer:
                context_str += f"- [{item['category']}]: \"{item['text'][:50]}...\"\n"
                last_category = item['category']
            context_str += "\n"

        # OPTIMIZATION: If regex says funny, and last category was funny/general, accept it.
        # But if last category was PRODUCT, we must check if this laughter belongs to it.
        if is_funny_regex and last_category != "product_related":
             return "funny", "regex"

        prompt = f"""Classify this text into ONE category.
Priority Order:
1. product_related (HIGHEST PRIORITY - code, work, tech, app, features, stock market, AI)
2. funny (jokes, laughter, banter)
3. general (casual conversation, life, random)

CRITICAL RULES:
- **CONTEXT IS KING**: If the user was just talking about 'product_related' stuff (see context), and now laughs or makes a short comment, IT IS STILL 'product_related'.
- Laughter ("hahaha", "lol") during a tech demo is 'product_related'.
- Only label 'funny' if the *topic* shifts entirely to a joke.
- If it mentions code/work AND is funny -> Label as 'product_related'.

Categories:
- product_related
- funny
- general

{context_str}CURRENT TEXT: "{text}"

Answer ONLY with the category name (lowercase)."""

        if provider == "together" and api_key:
            try:
                from together import Together
                client = Together(api_key=api_key)
                
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}]
                )
                
                content = response.choices[0].message.content.strip().lower()
                for cat in ["product_related", "funny", "general"]:
                    if cat in content:
                        return cat, "llm_context"
            except Exception as e:
                 print(f"⚠️ Together AI call failed: {e}")

        # 3. Final Fallback
        return "general", "fallback"

    def run(self):
        print("🏷️  Running Semantic Tagger (Context-Aware)...")
        
        if not os.path.exists(self.scores_path):
            print(f"⚠️ Scores file not found: {self.scores_path}")
            return
            
        with open(self.scores_path) as f:
            scores = json.load(f)
            
        if not self.load_model():
            return

        skipped_count = 0
        resumed_count = 0
        processed_count = 0
        step_name = "🏷️  Semantic Tagging"

        # Load existing tags to append/update
        if os.path.exists(self.output_path):
            try:
                with open(self.output_path) as f: tags = json.load(f)
            except: tags = {}
        else:
            tags = {}
        
        # We need to find the files
        # scores keys are clip_ids (filenames)
        # We look in 'processing/' recursively
        clip_paths = {}
        for root, _, files in os.walk("processing"):
            for f in files:
                if f.endswith(".mp4"):
                    clip_paths[f] = os.path.join(root, f)

        print(f"   Found {len(clip_paths)} processed clips available.")
        
        # KEY CHANGE: Sort keys to ensure temporal order for context
        # Assumes filenames are like 'chunk_0001.mp4' which sort lexicographically correctly
        sorted_clip_ids = sorted(scores.keys())
        
        context_buffer = [] # Sliding window of last 3 items
        
        for clip_id in sorted_clip_ids:
            metrics = scores[clip_id]
            
            # 1. Check Quality Threshold
            q_score = self.get_quality_score(metrics)
            
            if q_score < self.min_quality_threshold:
                # Skip low quality
                skipped_count += 1
                tags[clip_id] = {"category": "low_quality", "transcript": ""}
                continue
                
            # 2. Locate File
            path = clip_paths.get(clip_id)
            if not path:
                continue

            # RESUME CHECK
            # Even if resumed, we might need to READ the transcript to build context for NEXT chunk?
            # For simplicity, if resumed, we try to grab existing text for context.
            if state_manager.is_step_done(clip_id, step_name) and clip_id in tags:
                resumed_count += 1
                # Add to context buffer from EXISTING tag
                # Only if it has a real category
                existing_cat = tags[clip_id].get("category", "general")
                existing_text = tags[clip_id].get("transcript", "")
                if existing_cat != "low_quality":
                     context_buffer.append({"text": existing_text, "category": existing_cat})
                     if len(context_buffer) > 3:
                         context_buffer.pop(0)
                continue
                
            # 3. Transcribe
            print(f"   🎙️  Transcribing {clip_id} (Score: {q_score:.2f})...", end="\r")
            text = self.transcribe(path)
            
            # 4. Classify with Context
            category, attribution = self.classify_text(text, context_buffer)
            
            # Update Buffer
            context_buffer.append({"text": text, "category": category})
            if len(context_buffer) > 3:
                context_buffer.pop(0)
            
            tags[clip_id] = {
                "category": category,
                "transcript": text,
                "attribution": attribution
            }
            # Visual Progress for the user
            attr_label = f"[{attribution.upper()}]"
            print(f"   🏷️  {clip_id}: {category:15} {attr_label:10} \"{text[:30]}...\"")
            processed_count += 1
            state_manager.mark_step_done(clip_id, step_name)
            
        # Clear line
        print(f"                                                                 ", end="\r")
        print(f"✅ Tagging Complete.")
        print(f"   Processed: {processed_count}")
        print(f"   Resumed: {resumed_count}")
        print(f"   Skipped (Low Quality): {skipped_count}")
        
        with open(self.output_path, "w") as f:
            json.dump(tags, f, indent=2)
        print(f"   Tags saved to {self.output_path}")

if __name__ == "__main__":
    tagger = SemanticTagger()
    tagger.run()
