import json
import os
import shutil
import warnings
import sys
# Add project root to sys.path for modular imports
sys.path.append(os.getcwd())

import core.state as state_manager
from core import config as cfg_loader
from core import path_utils

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
        proc_dir = path_utils.get_processing_dir()
        self.scores_path = os.path.join(proc_dir, "scores.json")
        self.output_path = os.path.join(proc_dir, "semantic_tags.json")
        self.keywords_path = "data/keywords_active.json"
        self.keywords = self._load_keywords()
        self.api_key = self.config.get("semantic_model", {}).get("api_key") or os.getenv("TOGETHER_API_KEY")
        
        # Configuration for "Pre-Filtering"
        # We only transcribe clips that are "kinda good" to save time.
        self.min_quality_threshold = 0.4 # Lower than final keep threshold to be safe
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = None # Lazy load for Local fallback

    def _load_keywords(self):
        try:
            with open(self.keywords_path) as f:
                return json.load(f)
        except Exception:
            return {"product_related": [], "funny": []}

    def load_model(self):
        # Only load local model if strictly necessary (Lazy Loading is good)
        if self.model is None:
            print(f"🧠 Loading Local Whisper model (small) on {self.device} as fallback...")
            try:
                self.model = whisper.load_model("small", device=self.device)
            except Exception as e:
                print(f"❌ Failed to load Local Whisper: {e}")
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
        # 1. Try Together AI (Cloud Whisper Large v3) - High Quality & Fast
        if self.api_key:
            try:
                from together import Together
                client = Together(api_key=self.api_key)
                
                with open(clip_path, "rb") as audio_file:
                    response = client.audio.transcriptions.create(
                        model="openai/whisper-large-v3",
                        file=audio_file,
                        response_format="json"
                    )
                
                text = response.text.strip()
                return text
            except Exception as e:
                # Log cloud failure clearly so user knows fallback happened
                print(f"   ⚠️ Cloud Transcription failed ({e}), switching to local fallback...")
                pass
        
        # 2. Fallback to Local Whisper (Small) - Free/Offline
        if not self.load_model(): # Ensure model is loaded
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
        Now also extracts VISUAL POTENTIAL for B-Roll.
        """
        if not text:
             return "general", "too_short", 0, "", False, "empty_text"
        
        if len(text) < 2:
             # It was < 10, now < 2. Log what it was.
             return "general", "too_short", 0, "", False, f"too_short_{text}"

        # 1. Fast Regex/Keyword Check
        text_lower = text.lower()
        
        product_keywords = self.keywords.get("product_related", [])
        if any(w in text_lower for w in product_keywords):
            # If regex matches, we assume score 0 for safety unless we want to force LLM?
            # For B-Roll, we need visuals. Regex doesn't give visuals.
            # Strategy: If Regex hits, we default to "product_related" but NO visual description.
            # Strategy: If Regex hits, we default to "product_related" but NO visual description.
            return "product_related", "regex", 0, "", False, "regex_product"
            
        funny_keywords = self.keywords.get("funny", [])
        is_funny_regex = any(w in text_lower for w in funny_keywords)
        
        # 2. Together AI / LLM (The Judge & Visual Director)
        semantic_cfg = self.config.get("semantic_model", {})
        provider = semantic_cfg.get("provider", "local")
        api_key = semantic_cfg.get("api_key")
        model = semantic_cfg.get("model", "ServiceNow-AI/Apriel-1.6-15b-Thinker")

        # Build Context String (Last 6 chunks ~ 30s)
        context_str = ""
        last_category = "general"
        if context_buffer:
            context_str = "PREVIOUS CONTEXT (Use this to resolve fragmented sentences):\n"
            for item in context_buffer:
                context_str += f"- [{item['category']}]: \"{item['text'][:50]}...\"\n"
                last_category = item['category']
            context_str += "\n"

        if is_funny_regex and last_category != "product_related":
             return "funny", "regex", 0, "", False, "regex_funny"

        prompt = f"""Analyze this text for Category AND Visual Potential.
        
        CONTEXT: The text below is a 5-second fragment of a longer video. 
        Use the PREVIOUS CONTEXT to understand the topic if the fragment is incomplete.
        
        1. Classify Category (product_related, funny, general).
        2. Assign 'visual_score' (0-10): How easily can this be illustrated?
        3. Write 'visual_description': A prompt for an AI image generator.
           - IMPORTANT: Describe the MEANING, not just the words.
           - If text is "Falling from the top" (context: Market), describe "Stock market crash chart", NOT "Red ball falling".
           - Use 16:9 cinematic style description.
        4. DECIDE: 'b_roll_needed' (true/false).
           - True: Text describes concrete scenes, strong metaphors, or specific topics (Markets, Coding, Travel).
           - False: Filler words ("Uhh", "So basically"), pure abstraction, or fragmented sentences without clear meaning.
        
        {context_str}CURRENT FRAGMENT: "{text}"
        
        OUTPUT FORMAT (valid JSON only):
        {{
          "category": "category_name",
          "visual_score": 5, 
          "visual_description": "A description of the scene...",
          "b_roll_needed": true,
          "b_roll_reason": "Visualization adds value to 'red car'"
        }}
        """

        if provider == "together" and api_key:
            try:
                from together import Together
                client = Together(api_key=api_key)
                
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}]
                )
                
                content = response.choices[0].message.content.strip()
                # Parse JSON
                try: 
                    # Find JSON substring if model chats
                    start = content.find('{')
                    end = content.rfind('}') + 1
                    json_str = content[start:end]
                    data = json.loads(json_str)
                    
                    return (
                        data.get("category", "general"), 
                        "llm_context", 
                        data.get("visual_score", 0), 
                        data.get("visual_description", ""),
                        data.get("b_roll_needed", False),
                        data.get("b_roll_reason", "")
                    )
                except:
                     # Fallback if JSON fails
                     lower_content = content.lower()
                     cat = "general"
                     for c in ["product_related", "funny", "general"]:
                         if c in lower_content: cat = c
                     return cat, "llm_fallback", 0, "", False, "json_error"

            except Exception as e:
                 print(f"⚠️ Together AI call failed: {e}")

        # 3. Final Fallback
        return "general", "fallback", 0, "", False, "fallback"

    def run(self):
        print("🏷️  Running Semantic Tagger (Context-Aware)...")
        
        # Check if enabled in config
        semantic_cfg = self.config.get("semantic_policy", {})
        llm_enabled = semantic_cfg.get("enabled", False)
        
        if not llm_enabled:
             print("   ⏩ LLM Tagging Disabled. Running Transcription Only (for Thumbnail).")

        if not os.path.exists(self.scores_path):
            print(f"⚠️ Scores file not found: {self.scores_path}")
            return
            
        with open(self.scores_path) as f:
            scores = json.load(f)
        
        # OPTIMIZATION: Do NOT load local model here. 
        # Let transcribe() load it lazily only if Cloud fails.
        # if not self.load_model(): return


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
        # scores keys are clip_ids (filenames/paths like 'segment_0000/chunk_0000.mp4')
        # We look in user's processing subfolder
        proc_dir = path_utils.get_processing_dir()
        clip_paths = {}
        for root, _, files in os.walk(proc_dir):
            for f in files:
                if f.endswith(".mp4"):
                    full_path = os.path.join(root, f)
                    rel_path = os.path.relpath(full_path, proc_dir)
                    clip_paths[rel_path] = full_path

        print(f"   Found {len(clip_paths)} processed clips available.")
        
        # KEY CHANGE: Sort keys to ensure temporal order for context
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

            # RESUME CHECK: Trust File Cache > State Manager
            # If we have a tag in the JSON file, assume it's done, even if state_manager forgot.
            if clip_id in tags:
                # Check if it has valid data (not just a placeholder)
                if tags[clip_id].get("category"):
                    resumed_count += 1
                    # Auto-repair state
                    state_manager.update_chunk_status(clip_id, "COMPLETED", step=step_name)
                    # print(f"   ⏩ Resuming {clip_id} from cache.") 
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
            
            # 4. Classify (Conditional)
            visual_score = 0
            visual_desc = ""
            
            if llm_enabled:
                # Expecting 6 values: cat, attr, v_score, v_desc, br_need, br_reason
                result = self.classify_text(text, context_buffer)
                if len(result) == 6:
                    category, attribution, visual_score, visual_desc, br_needed, br_reason = result
                elif len(result) == 4:
                     category, attribution, visual_score, visual_desc = result
                     br_needed, br_reason = False, "legacy_4"
                else:
                     category, attribution = result[:2]
                     br_needed, br_reason = False, "legacy_2"
            else:
                # Fast path
                category = "general"
                attribution = "fast_mode"
                br_needed = False
                br_reason = "fast_mode_disabled"
                
                # Basic Keyword Check
                text_lower = text.lower()
                product_keywords = self.keywords.get("product_related", [])
                funny_keywords = self.keywords.get("funny", [])
                
                if any(w in text_lower for w in product_keywords):
                    category = "product_related"
                    attribution = "regex_fast"
                elif any(w in text_lower for w in funny_keywords):
                    category = "funny"
                    attribution = "regex_fast"
            
            # Update Buffer
            context_buffer.append({"text": text, "category": category})
            if len(context_buffer) > 6:
                context_buffer.pop(0)
            
            tags[clip_id] = {
                "category": category,
                "transcript": text,
                "attribution": attribution,
                "visual_score": visual_score,
                "visual_description": visual_desc,
                "b_roll_needed": br_needed,
                "b_roll_reason": br_reason
            }
            # Visual Progress for the user
            attr_label = f"[{attribution.upper()}]"
            v_label = f"(V:{visual_score})" if visual_score >= 7 else ""
            print(f"   🏷️  {clip_id}: {category:15} {attr_label:10} {v_label:6} \"{text[:30]}...\"")
            processed_count += 1
            state_manager.mark_step_done(clip_id, step_name)
            
            # INCREMENTAL SAVE (Every 5 clips) to allow resume on crash
            if processed_count % 5 == 0:
                with open(self.output_path, "w") as f:
                    json.dump(tags, f, indent=2)
            
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
