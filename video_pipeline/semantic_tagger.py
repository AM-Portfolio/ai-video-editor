import json
import os
import shutil
import warnings
import sys

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
    def __init__(self, config_path="config.json"):
        self.config = self._load_config(config_path)
        self.scores_path = "processing/scores.json"
        self.output_path = "processing/semantic_tags.json"
        
        # Configuration for "Pre-Filtering"
        # We only transcribe clips that are "kinda good" to save time.
        self.min_quality_threshold = 0.4 # Lower than final keep threshold to be safe
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = None # Lazy load

    def _load_config(self, path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            return {}

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
            # Whisper transcribes audio/video files directly
            result = self.model.transcribe(clip_path, fp16=(self.device=="cuda"))
            text = result.get("text", "").strip()
            return text
        except Exception as e:
            print(f"   ⚠️ Transcription failed for {os.path.basename(clip_path)}: {e}")
            return ""

    def classify_text(self, text):
        """
        Uses Regex/Keywords FIRST, then falls back to Together AI.
        Categories: product_related, funny, general
        """
        if not text or len(text) < 10:
            return "general" 

        # 1. Fast Regex/Keyword Check
        text_lower = text.lower()
        
        # Product Related (Code, Work, Explanation) - English + Hinglish
        product_keywords = [
            # English
            "code", "api", "function", "bug", "deploy", "python", "script", "json", 
            "token", "import ", "class ", "meeting", "agenda", "client", "project", 
            "timeline", "deadline", "quarter", "revenue", "feature", "app", 
            "so basically", "means that", "reason is",
            
            # Hinglish Tech/Work
            "chal gaya", "run ho gaya", "error aa raha hai", "phat gaya", "test karna", 
            "deploy kar do", "fix kar diya", "kaam hai", "urgent hai", "dead line", 
            "commit kiya", "push kiya", "file bhejo", "check kar lo", "samajh nahi aaya",
            "kaise chalega", "sahi chal raha hai", "issue hai", "server down", "bhai code",
            "logic kya hai", "build ban gaya", "repo share", "merge kar", "pull request"
        ]
        if any(w in text_lower for w in product_keywords):
            return "product_related"
            
        # Funny - English + Hinglish
        funny_keywords = [
            # English
            "haha", "lol", "funny", "lmao", "rofl", "joke", "kidding",
            
            # Hinglish
            "mazak", "kya baat hai", "mast joke", "arre bhai", "pagal hai kya", 
            "gazab", "bawal", "sahi khel gaya", "kya scene hai", "has mat",
            "lol bhai", "epic tha", "bakwas mat kar", "chutiyapa", "hasna mat"
        ]
        if any(w in text_lower for w in funny_keywords):
            return "funny"
        
        # 2. Together AI Fallback (for subtle context)
        semantic_cfg = self.config.get("semantic_model", {})
        provider = semantic_cfg.get("provider", "local")
        api_key = semantic_cfg.get("api_key")
        model = semantic_cfg.get("model", "ServiceNow-AI/Apriel-1.6-15b-Thinker")

        prompt = f"""Classify this text into ONE category.
Priority Order (if multiple match):
1. product_related (HIGHEST PRIORITY - code, work, tech, app, features)
2. funny (jokes, laughter, banter)
3. general (casual conversation, life, random)

Rules:
- If it mentions code/work AND is funny -> Label as 'product_related'.
- If it is funny AND general -> Label as 'funny'.
- Only label 'general' if it fits nothing else.

Categories:
- product_related
- funny
- general

Text: "{text}"

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
                        return cat
            except Exception as e:
                 print(f"⚠️ Together AI call failed: {e}")

        # 3. Final Fallback
        return "general" 

    def run(self):
        print("🏷️  Running Semantic Tagger...")
        
        if not os.path.exists(self.scores_path):
            print(f"⚠️ Scores file not found: {self.scores_path}")
            return
            
        with open(self.scores_path) as f:
            scores = json.load(f)
            
        if not self.load_model():
            return

        tags = {}
        processed_count = 0
        skipped_count = 0
        
        # We need to find the files
        # scores keys are clip_ids (filenames)
        # We look in 'processing/' recursively
        clip_paths = {}
        for root, _, files in os.walk("processing"):
            for f in files:
                if f.endswith(".mp4"):
                    clip_paths[f] = os.path.join(root, f)

        print(f"   Found {len(clip_paths)} processed clips available.")
        
        for clip_id, metrics in scores.items():
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
                
            # 3. Transcribe
            print(f"   🎙️  Transcribing {clip_id} (Score: {q_score:.2f})...", end="\r")
            text = self.transcribe(path)
            
            # 4. Classify
            category = self.classify_text(text)
            
            tags[clip_id] = {
                "category": category,
                "transcript": text
            }
            processed_count += 1
            # print(f"   🏷️  {clip_id}: [{category}] \"{text[:30]}...\"")
            
        # Clear line
        print(f"                                                                 ", end="\r")
        print(f"✅ Tagging Complete.")
        print(f"   Processed: {processed_count}")
        print(f"   Skipped (Low Quality): {skipped_count}")
        
        with open(self.output_path, "w") as f:
            json.dump(tags, f, indent=2)
        print(f"   Tags saved to {self.output_path}")

if __name__ == "__main__":
    tagger = SemanticTagger()
    tagger.run()
