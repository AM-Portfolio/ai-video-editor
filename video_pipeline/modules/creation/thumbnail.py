import os
import json
import sys
import base64
# Add project root to sys.path
sys.path.append(os.getcwd())

from core import config as cfg_loader
from core import path_utils

try:
    from together import Together
except ImportError:
    print("❌ Missing `together`. Please run: pip install together")
    sys.exit(1)

class ThumbnailGenerator:
    def __init__(self, config_path=None):
        self.config = cfg_loader.load_config(config_path)
        self.proc_dir = path_utils.get_processing_dir()
        self.output_dir = path_utils.get_output_videos_dir()
        
        # Load API Key (Reuse TOGETHER_API_KEY from Tagging)
        # Priority: Config > Env Var
        self.api_key = self.config.get("semantic_model", {}).get("api_key") or os.getenv("TOGETHER_API_KEY")
        
        if not self.api_key:
            print("⚠️ No API Key found for Together AI. Set TOGETHER_API_KEY env var.")
            self.client = None
        else:
            self.client = Together(api_key=self.api_key)

    def generate_prompt_from_transcript(self, tags_path):
        """
        Reads semantic_tags.json, aggregates transcripts, and truncates.
        """
        if not os.path.exists(tags_path):
            return None
            
        with open(tags_path, 'r') as f:
            tags = json.load(f)
            
        # Aggregate text
        full_text = ""
        for clip, data in tags.items():
            if data.get("transcript"):
                full_text += data["transcript"] + " "
                
        if not full_text:
            return None
            
        # Truncate to ~4000 chars for prompt safety
        truncated_text = full_text[:4000]
        return truncated_text

    def get_best_face_frame(self, scores_path):
        """
        Finds the clip with the highest face_score and extracts the middle frame.
        FALLBACK: If no face scores exist, scan clips on the fly!
        """
        proc_dir = path_utils.get_processing_dir()
        best_clip = None
        max_score = -1.0
        
        # 1. Try Loading Existing Scores
        if os.path.exists(scores_path):
            try:
                with open(scores_path) as f: scores = json.load(f)
                for clip_id, metrics in scores.items():
                    fs = metrics.get("face_score", 0.0)
                    if fs > max_score:
                        max_score = fs
                        best_clip = clip_id
            except: pass
            
        # 2. JIT Fallback: If no score found, we must scan!
        if not best_clip or max_score < 0.05:
            print("   ⚠️ No existing face scores found. Running Just-In-Time Scan...")
            # Quickly scan first 3 clips to find a face
            import cv2
            try:
                import mediapipe as mp
                from mediapipe.tasks import python
                from mediapipe.tasks.python import vision
                
                # Setup Detector
                # FIX: core.path_utils does NOT have get_model_path, using raw path
                model_path = os.path.join(path_utils.ROOT_DIR, "data", "detector.tflite")
                if not os.path.exists(model_path):
                     # Try local path
                     model_path = "data/detector.tflite"

                if os.path.exists(model_path):
                    base_options = python.BaseOptions(model_asset_path=model_path)
                    options = vision.FaceDetectorOptions(base_options=base_options, min_detection_confidence=0.3)
                    detector = vision.FaceDetector.create_from_options(options)
                    
                    # Scan clips
                    candidates = []
                    for root, _, files in os.walk(proc_dir):
                        for file in files:
                            if file.endswith(".mp4") and "segment_" in root:
                                candidates.append(os.path.join(root, file))
                    
                    # Sort candidates to look at early/important clips first
                    candidates.sort()
                    candidates = candidates[:10] # Limit to 10 to save time
                    
                    for clip_p in candidates:
                        cap = cv2.VideoCapture(clip_p)
                        frames_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                        # Sample middle frame
                        cap.set(cv2.CAP_PROP_POS_FRAMES, frames_count // 2)
                        ret, frame = cap.read()
                        cap.release()
                        
                        if ret:
                            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
                            result = detector.detect(mp_image)
                            
                            if result.detections:
                                score = result.detections[0].categories[0].score
                                if score > max_score:
                                    max_score = score
                                    best_clip = os.path.basename(clip_p) # Just filename for consistency
                                    print(f"      Found face in {best_clip} (Score: {score:.2f})")
                                    if score > 0.7: break # Good enough
                else:
                    print("      ❌ Missing detector model for JIT scan.")
            except ImportError:
                 print("      ❌ Missing mediapipe for JIT scan.")
            except Exception as e:
                 print(f"      ❌ JIT Scan failed: {e}")

        clip_path = None
        if not best_clip or max_score < 0.05:
            print(f"   ⚠️ Still no good face found (Max Score: {max_score:.2f}).")
            
            # FALLBACK OF LAST RESORT: Pick ANY frame from the first available clip
            print("   🧨 FALLBACK: Picking random frame from first clip (User Request).")
            for root, _, files in os.walk(proc_dir):
                for f in files:
                    if f.endswith(".mp4") and "segment_" in root:
                         clip_path = os.path.join(root, f)
                         best_clip = f # Just for logging
                         break
                if clip_path: break
            
            if not clip_path:
                return None, None
                
        else:
            # Normal Path: Find file for the best clip
            for root, _, files in os.walk(proc_dir):
                 if best_clip in files:
                     clip_path = os.path.join(root, best_clip)
                     break
                     
        if not clip_path: return None, None
            
        try:
            import cv2
            cap = cv2.VideoCapture(clip_path)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            cap.set(cv2.CAP_PROP_POS_FRAMES, total_frames // 2) 
            ret, frame = cap.read()
            cap.release()
            
            if ret:
                _, buffer = cv2.imencode('.jpg', frame)
                b64_img = base64.b64encode(buffer).decode('utf-8')
                return b64_img, best_clip
        except: return None, None
            
        return None, None

    def run(self):
        print("🎨 Generating YouTube Thumbnail (Together AI 2-Stage [Raw])...")
        
        if not self.api_key:
            print("❌ Skipping: No API Key.")
            return

        tags_path = os.path.join(self.proc_dir, "semantic_tags.json")
        scores_path = os.path.join(self.proc_dir, "scores.json")
        
        transcript_text = self.generate_prompt_from_transcript(tags_path)
        
        if not transcript_text:
            print("⚠️ No transcript found to generate thumbnail.")
            return

        # Initialize Together SDK for TEXT (It works fine for text)
        try:
             from together import Together
             client = Together(api_key=self.api_key)
        except:
             print("❌ Together SDK broken, cannot summarize.")
             return

        # STEP 1: Summarize Transcript (Text Model)
        text_model = self.config.get("semantic_model", {}).get("model", "ServiceNow-AI/Apriel-1.6-15b-Thinker")
        print(f"   ✍️  Summarizing transcript with {text_model}...")
        
        summary_prompt = f"""
        Read the following video transcript and write a SHORT, VISUAL description for a YouTube thumbnail.
        focus on the main subject, action, and mood.
        
        Transcript:
        {transcript_text[:3000]}... (Truncated)
        
        OUTPUT FORMAT:
        "A [style] image of [subject] [action], [lighting], [mood]."
        Keep it under 50 words.
        """
        
        visual_prompt = "A professional YouTube thumbnail."
        try:
            response = client.chat.completions.create(
                model=text_model,
                messages=[{"role": "user", "content": summary_prompt}]
            )
            visual_prompt = response.choices[0].message.content.strip()
            print(f"   📝 Visual Prompt: \"{visual_prompt}\"")
        except Exception as e:
             print(f"   ⚠️ Summarization failed ({e}).")

        # STEP 1.5: Analyze Best Face (Vision Model)
        face_desc = ""
        b64_face, face_clip = self.get_best_face_frame(scores_path)
        
        if b64_face:
            print(f"   👤 Analyzing Best Face from {face_clip} (Vision)...")
            try:
                # Use Llama 3.2 90B Vision (More likely to be available/serverless)
                vision_model = "meta-llama/Llama-3.2-90B-Vision-Instruct-Turbo"
                
                vision_response = client.chat.completions.create(
                    model=vision_model,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "Describe the person in this image in detail (Appearance, Hair, Glasses, Clothing, Expression). Be concise."},
                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_face}"}}
                            ]
                        }
                    ],
                )
                face_desc = vision_response.choices[0].message.content.strip()
                print(f"   😎 Face Description: \"{face_desc[:50]}...\"")
            except Exception as e:
                print(f"   ⚠️ Vision analysis failed: {e}")

        # STEP 2: Generate Image (FLUX.2-max via RAW REQUESTS)
        # FLUX supports Image-to-Image, so we re-enable image_url!
        import requests
        
        final_prompt = f"Create a high-quality YouTube thumbnail. \nScene: {visual_prompt}"
        if face_desc:
             final_prompt += f"\nCharacter Details: {face_desc}"
            
        print(f"   🎨 Final Prompt: {final_prompt[:100]}...")
        print("   ✨ Calling Together AI (FLUX.2-max Img2Img)...")
        
        url = "https://api.together.xyz/v1/images/generations"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "Rundiffusion/Juggernaut-Lightning-Flux",
            "prompt": final_prompt,
            "negative_prompt": "blurry, low quality, distorted face, ugly, text watermark, bad composition",
            "response_format": "b64_json",
            "disable_safety_checker": True,
            "width": 1024, # Optimized for Lightning
            "height": 576,
            "steps": 4 # Lightning needs fewer steps
        }
        
        # Inject Image (DISABLED for Juggernaut-Lightning as requested)
        if b64_face:
            print(f"   📸 Img2Img Disabled for new model. Using Text-Only generation.")
            # payload["image_url"] = f"data:image/jpeg;base64,{b64_face}"
            
        try:
            response = requests.post(url, json=payload, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                if "data" in data and len(data["data"]) > 0:
                    b64_json = data["data"][0]["b64_json"]
                    image_data = base64.b64decode(b64_json)
                    p = os.path.join(self.output_dir, "thumbnail.png")
                    with open(p, "wb") as f: f.write(image_data)
                    print(f"   ✅ Thumbnail saved: {p}")
                else:
                    print(f"   ⚠️ No image data in response: {data}")
            else:
                print(f"   ❌ API Error {response.status_code}: {response.text}")

        except Exception as e:
            print(f"   ❌ Thumbnail generation failed: {e}")

if __name__ == "__main__":
    gen = ThumbnailGenerator()
    gen.run()
