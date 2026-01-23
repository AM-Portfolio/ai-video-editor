import streamlit as st
import os
import json
import threading
from queue import Queue
import time
import run_pipeline

# Page Config
st.set_page_config(
    page_title="AI Video Editor",
    page_icon="🎥",
    layout="wide"
)

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_CLIPS_DIR = os.path.join(BASE_DIR, "input_clips")
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
FINAL_OUTPUT_DIR = os.path.join(BASE_DIR, "output_clips")

# Ensure directories exist
os.makedirs(INPUT_CLIPS_DIR, exist_ok=True)

def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r') as f:
            return json.load(f)
    return {}

def save_config(new_config):
    with open(CONFIG_PATH, 'w') as f:
        json.dump(new_config, f, indent=4)

def main():
    st.title("🎥 AI Video Editor Pipeline")
    st.markdown("Upload raw footage, configure AI settings, and generate a polished video.")

    # Sidebar: Configuration
    st.sidebar.header("⚙️ Configuration")
    
    config = load_config()
    
    # Silence Settings
    st.sidebar.subheader("✂️ Auto-Cut Silence")
    
    # Handle potentially string-based silence_db (e.g., "-30dB")
    raw_silence = config.get("silence_db", -30)
    if isinstance(raw_silence, str):
        try:
            raw_silence = int(raw_silence.replace("dB", "").strip())
        except ValueError:
            raw_silence = -30
            
    silence_db = st.sidebar.slider("Silence Threshold (dB)", -60, -10, int(raw_silence))
    silence_duration = st.sidebar.number_input("Min Silence Duration (s)", 0.1, 5.0, float(config.get("silence_duration", 0.5)))
    
    # Privacy Blur Settings
    st.sidebar.divider()
    st.sidebar.subheader("🔒 Privacy Blur")
    blur_enabled = st.sidebar.checkbox("Enable Privacy Blur", config.get("privacy_blur", {}).get("enabled", False))
    blur_mode = st.sidebar.selectbox(
        "Blur Mode", 
        ["face_blur", "region_blur"], 
        index=0 if config.get("privacy_blur", {}).get("mode") == "face_blur" else 1
    )
    blur_strength = st.sidebar.slider("Blur Strength", 1, 100, config.get("privacy_blur", {}).get("blur_strength", 25))
    exclude_main_face = st.sidebar.checkbox("Exclude Main Speaker", config.get("privacy_blur", {}).get("exclude_main_face", True))

    # Save Config Button
    if st.sidebar.button("💾 Save Settings"):
        config["silence_db"] = silence_db
        config["silence_duration"] = silence_duration
        if "privacy_blur" not in config: config["privacy_blur"] = {}
        config["privacy_blur"]["enabled"] = blur_enabled
        config["privacy_blur"]["mode"] = blur_mode
        config["privacy_blur"]["blur_strength"] = blur_strength
        config["privacy_blur"]["exclude_main_face"] = exclude_main_face
        save_config(config)
        st.sidebar.success("Settings saved!")

    # Main Area: File Upload
    uploaded_file = st.file_uploader("Upload a Video (.mp4)", type=["mp4"])
    
    if uploaded_file is not None:
        # Save uploaded file to input_clips
        file_path = os.path.join(INPUT_CLIPS_DIR, uploaded_file.name)
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        st.success(f"✅ Uploaded: {uploaded_file.name}")
        
        if st.button("🚀 Run AI Pipeline"):
            st.divider()
            
            # Progress bar
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # Use a container for the logs
            with st.status("🚀 Starting Pipeline...", expanded=True) as status:
                
                # Callback to update UI logs
                context = {"step_count": 0, "total_steps": 7} # Approx total steps
                
                def ui_logger(message):
                    # Strict Filter: Only allow Headlines and Important Code Blocks
                    allowed_emojis = ["🚀", "✂️", "🏃", "🗣️", "👤", "🔒", "🕵️", "🎞️", "✨", "📥", "❌", "🛑"]
                    
                    is_headline = any(e in message for e in allowed_emojis)
                    is_success = "✅" in message
                    is_moved = "Moved" in message and "files" in message
                    
                    # Exclude specific noisy patterns
                    is_noise = any(x in message for x in ["->", "Loading", "Scanning", "Analyzing", "Using cache", "GL version", "TensorFlow"])
                    
                    if (is_headline or is_success or is_moved) and not is_noise:
                        st.write(message) # Render as markdown/text inside status
                        
                        # Update progress bar based on step completion
                        if "✅" in message and "finished" in message:
                            context["step_count"] += 1
                            progress = min(context["step_count"] / context["total_steps"], 1.0)
                            progress_bar.progress(progress)
                        
                        # Update status label for current step
                        if is_headline and not "finished" in message:
                            # Strip fancy formatting if needed or just use the message
                            clean_label = message.strip().replace("=", "").strip()
                            if clean_label:
                                status.update(label=clean_label, state="running")

                # Run pipeline
                run_pipeline.main(logger_callback=ui_logger)
                
                # Finalize
                status.update(label="✨ Pipeline Completed!", state="complete", expanded=False)
                progress_bar.progress(1.0)
            
            st.success("🎉 Processing Complete!")
            
            # Check for output videos
            if os.path.exists(FINAL_OUTPUT_DIR):
                video_files = [f for f in os.listdir(FINAL_OUTPUT_DIR) if f.startswith("final_") and f.endswith(".mp4")]
                video_files.sort(key=lambda x: os.path.getmtime(os.path.join(FINAL_OUTPUT_DIR, x)), reverse=True)
                
                if video_files:
                    st.divider()
                    st.subheader("🎞️ Final Result")
                    latest_video = os.path.join(FINAL_OUTPUT_DIR, video_files[0])
                    st.video(latest_video)
                    
                    with open(latest_video, "rb") as video_file:
                        st.download_button(
                            label="⬇️ Download Final Video",
                            data=video_file,
                            file_name=os.path.basename(latest_video),
                            mime="video/mp4"
                        )
                else:
                    st.warning("No output file found. Check logs for errors.")

if __name__ == "__main__":
    main()
