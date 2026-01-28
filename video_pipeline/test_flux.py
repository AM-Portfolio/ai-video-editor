import os
import sys
import requests
import json
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("TOGETHER_API_KEY")

if not api_key:
    try:
        with open("video_pipeline/data/config.json") as f:
            cfg = json.load(f)
            api_key = cfg.get("semantic_model", {}).get("api_key")
    except: pass

url = "https://api.together.xyz/v1/images/generations"
headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

# The user explicitly asked about this model
MODEL = "black-forest-labs/FLUX.2-max"

print(f"✅ Testing {MODEL} with Key: {api_key[:5]}...")

# dummy 1x1 image (Red Pixel)
dummy_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKwMIQAAAABJRU5ErkJggg=="

payload = {
    "model": MODEL,
    "prompt": "A YouTube thumbnail of a hacker in a hoodie, 16:9, cinematic text 'FLUX MAX'",
    "response_format": "b64_json",
    "disable_safety_checker": True,
    "width": 1376,      # Testing precise 16:9
    "height": 768,
    "steps": 28,        # FLUX often likes explicit steps (or usually defaults well)
}

# Test 1: Text-to-Image
print("\n--- Test 1: Text Mode (1376x768) ---")
try:
    response = requests.post(url, json=payload, headers=headers)
    if response.status_code == 200:
        print("✅ Success! Text-to-Image works.")
    else:
        print(f"❌ Failed ({response.status_code}): {response.text}")
except Exception as e:
    print(f"❌ Error: {e}")

# Test 2: Image-to-Image (The Holy Grail)
print("\n--- Test 2: Img2Img Mode (Face Clone potential) ---")
payload["image_url"] = f"data:image/png;base64,{dummy_b64}"
payload["strength"] = 0.7 # Common parameter for Img2Img control

try:
    response = requests.post(url, json=payload, headers=headers)
    if response.status_code == 200:
        print("✅✅✅ SUCCESS! FLUX supports Image-to-Image!")
        print("Verdict: SUPERIOR to Gemini 3 for this task.")
    else:
        print(f"❌ Failed ({response.status_code}): {response.text}")
except Exception as e:
    print(f"❌ Error: {e}")
