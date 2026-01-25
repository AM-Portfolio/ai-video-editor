import streamlit as st
import os
import json
import threading
from queue import Queue
import time
import run_pipeline
import subprocess
import shutil

# Page Config
st.set_page_config(
    page_title="AI Video Editor",
    page_icon="🎥",
    layout="wide"
)

# Paths (Dynamic Base)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
from core.scoring import ScoreKeeper
from core import state as state_manager
from core import config as cfg_loader
from core import path_utils


DEFAULT_CONFIG = {
    "silence_db": -30,
    "silence_duration": 0.5,
    "privacy_blur": {
        "enabled": False,
        "mode": "face_blur",
        "blur_strength": 25,
        "exclude_main_face": True
    },
    "decider": {
        "keep_threshold": 0.50,
        "weights": {"face": 0.1, "motion": 0.2, "speech": 0.7}
    },
    "semantic_policy": {
        "weights": {"product_related": 1.0, "funny": 1.0, "general": 0.9}
    },
    "self_learning": True
}

def load_config():
    # Config is currently global, but maybe should be per-user?
    # For MVP, shared config is acceptable, or use user folder.
    # Let's use global config for now to keep it simple.
    CONFIG_PATH = os.path.join(BASE_DIR, "data", "config.json")
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r') as f:
                return json.load(f)
        except: return DEFAULT_CONFIG.copy() # Fallback
    return DEFAULT_CONFIG.copy() # Default

def save_config(new_config):
    CONFIG_PATH = os.path.join(BASE_DIR, "data", "config.json")
    try:
        with open(CONFIG_PATH, 'w') as f:
            json.dump(new_config, f, indent=4)
    except: pass

def main():
    st.title("🎥 AI Video Editor Pipeline")
    
    # ---------------------------------------------------------
    # 🔐 AUTHENTICATION LAYER
    # ---------------------------------------------------------
    if "user_id" not in st.session_state:
        st.markdown("### 🔐 Login to Studio")
        with st.form("login_form"):
            user_input = st.text_input("Enter Session Name / User ID", placeholder="e.g. creative_director_01")
            submitted = st.form_submit_button("Start Session")
            if submitted and user_input:
                st.session_state["user_id"] = user_input.strip().replace(" ", "_")
                st.rerun()
        st.info("👋 This is a multi-user system. Your data is isolated by your Session ID.")
        return

    user_id = st.session_state["user_id"]
    st.sidebar.markdown(f"👤 **User:** `{user_id}`")
    if st.sidebar.button("🚪 Logout"):
        del st.session_state["user_id"]
        st.rerun()

    # ---------------------------------------------------------
    # 📂 USER PATHS (Segregated)
    # ---------------------------------------------------------
    INPUT_CLIPS_DIR = path_utils.get_input_clips_dir()
    FINAL_OUTPUT_DIR = path_utils.get_output_clips_dir()
    PROCESSING_DIR = path_utils.get_processing_dir()
    OUTPUT_VIDEOS_DIR = path_utils.get_output_videos_dir()
    
    # Legacy alias for display logic
    FINAL_VIDEO_DIR = OUTPUT_VIDEOS_DIR
    
    # Ensure User Dirs
    os.makedirs(INPUT_CLIPS_DIR, exist_ok=True)
    
    st.markdown(f"Upload raw footage to your workspace (`{user_id}`), configure AI settings, and generate a polished video.")

    # Sidebar: Configuration
    st.sidebar.header("⚙️ Configuration")
    try:
        max_upload = st.config.get_option("server.maxUploadSize")
        st.sidebar.caption(f"Max Upload Size: {max_upload}MB")
    except:
        pass
    
    config = load_config()
    
    # Silence Settings
    st.sidebar.subheader("✂️ Auto-Cut Silence")
    raw_silence = config.get("silence_db", -30)
    if isinstance(raw_silence, str):
        try: raw_silence = int(raw_silence.replace("dB", "").strip())
        except: raw_silence = -30
    silence_db = st.sidebar.slider(
        "Silence Threshold (dB)", -60, -10, int(raw_silence),
        help="Volume level considered 'silence'. \n- **Lower (-60dB)**: Sensitive, detects faint whispers.\n- **Higher (-10dB)**: Strict, background noise is ignored."
    )
    silence_duration = st.sidebar.number_input(
        "Min Silence Duration (s)", 0.1, 5.0, float(config.get("silence_duration", 0.5)),
        help="Minimum duration of quietness required to trigger a cut.\n- **Increase**: To keep natural pauses in speech.\n- **Decrease**: For tighter, faster-paced cuts."
    )

    # Privacy Blur Settings
    st.sidebar.divider()
    st.sidebar.subheader("🔒 Privacy Blur")
    blur_enabled = st.sidebar.checkbox(
        "Enable Privacy Blur", config.get("privacy_blur", {}).get("enabled", False),
        help="If enabled, the AI will detect and blur sensitive regions (faces/text) to protect privacy."
    )
    blur_mode = st.sidebar.selectbox(
        "Blur Mode", 
        ["face_blur", "text_blur", "region_blur"], 
        index=0 if config.get("privacy_blur", {}).get("mode") == "face_blur" else 1 if config.get("privacy_blur", {}).get("mode") == "text_blur" else 2,
        help="**Face**: Blurs people.\n**Text**: Blurs overlay text/screens.\n**Region**: Blurs specific coordinates."
    )
    blur_strength = st.sidebar.slider(
        "Blur Strength", 1, 100, config.get("privacy_blur", {}).get("blur_strength", 25),
        help="Intensity of the blur effect.\n- **Higher**: More opaque/pixelated.\n- **Lower**: Softer, semi-transparent."
    )
    exclude_main_face = st.sidebar.checkbox(
        "Exclude Main Speaker", config.get("privacy_blur", {}).get("exclude_main_face", True),
        help="Smart Safe-List: Attempts to identify the active speaker and keeps their face clear, while blurring others in the background."
    )

    # Decider Policy Settings
    st.sidebar.divider()
    st.sidebar.subheader("⚖️ Decider Policy")
    keep_threshold = st.sidebar.slider(
        "Keep Threshold", 0.0, 1.0, float(config.get("decider", {}).get("keep_threshold", 0.50)),
        help="Quality Control Gate.\n- **High (0.8+)**: Keeps only 5-Star perfect clips.\n- **Low (0.3)**: Include rough drafts and average shots."
    )
    
    st.sidebar.caption("Scoring Weights (Sum should be 1.0 ideally)")
    w_face = st.sidebar.slider(
        "Face Visibility Weight", 0.0, 1.0, float(config.get("decider", {}).get("weights", {}).get("face", 0.1)),
        help="Importance of seeing a clear face.\nIncrease this for interview/vlog content."
    )
    w_motion = st.sidebar.slider(
        "Motion Weight", 0.0, 1.0, float(config.get("decider", {}).get("weights", {}).get("motion", 0.2)),
        help="Importance of movement.\nIncrease this for action sports or dynamic B-Roll."
    )
    w_speech = st.sidebar.slider(
        "Speech Presence Weight", 0.0, 1.0, float(config.get("decider", {}).get("weights", {}).get("speech", 0.7)),
        help="Importance of audio/dialogue.\nHigh values prioritize clips with clear talking."
    )

    # Semantic Policy Settings
    st.sidebar.divider()
    st.sidebar.subheader("🏷️ Semantic Weights")
    s_product = st.sidebar.slider(
        "Product Related Influence", 0.0, 1.0, float(config.get("semantic_policy", {}).get("weights", {}).get("product_related", 1.0)),
        help="How much the AI prompts 'Product Features', 'Demo', or 'Unboxing'."
    )
    s_funny = st.sidebar.slider(
        "Funny Influence", 0.0, 1.0, float(config.get("semantic_policy", {}).get("weights", {}).get("funny", 1.0)),
        help="How much the AI hunts for jokes, laughter, or funny errors."
    )
    s_general = st.sidebar.slider(
        "General Content Influence", 0.0, 1.0, float(config.get("semantic_policy", {}).get("weights", {}).get("general", 0.9)),
        help="Baseline interest in standard storytelling clips."
    )

    # Learning Policy
    st.sidebar.divider()
    st.sidebar.subheader("🤖 Intelligence")
    self_learning = st.sidebar.checkbox(
        "Enable Self-Learning", config.get("self_learning", True), 
        help="If enabled, the AI analyzes its own results to discover NEW keywords from your footage to use in future runs."
    )

    # Save Config Button
    if st.sidebar.button("💾 Save Settings"):
        config["silence_db"] = silence_db
        config["silence_duration"] = silence_duration
        if "privacy_blur" not in config: config["privacy_blur"] = {}
        config["privacy_blur"]["enabled"] = blur_enabled
        config["privacy_blur"]["mode"] = blur_mode
        config["privacy_blur"]["blur_strength"] = blur_strength
        config["privacy_blur"]["exclude_main_face"] = exclude_main_face
        
        # New Decider Weights
        if "decider" not in config: config["decider"] = {}
        config["decider"]["keep_threshold"] = keep_threshold
        config["decider"]["weights"] = {"face": w_face, "motion": w_motion, "speech": w_speech}
        
        # New Semantic Weights
        if "semantic_policy" not in config: config["semantic_policy"] = {}
        config["semantic_policy"]["weights"] = {"product_related": s_product, "funny": s_funny, "general": s_general}
        
        config["self_learning"] = self_learning

        save_config(config)
        st.sidebar.success("Settings saved!")

    if st.sidebar.button("♻️ Reset to Defaults"):
        save_config(DEFAULT_CONFIG)
        st.success("Configuration reset to defaults!")
        time.sleep(0.5)
        st.rerun()

    # Main Area: File Upload
    
    def merge_and_display_result(base_name="video"):
        # Check for output videos folder
        if not os.path.exists(FINAL_OUTPUT_DIR):
            st.warning("No output directory found. Processing may still be in progress.")
            return

        CATEGORIES = ["product_related", "funny", "general"]
        
        st.divider()
        st.subheader("🏁 Final Categorized Results")
        
        # Load clip metadata if exists for rich info
        tags_path = os.path.join(PROCESSING_DIR, "semantic_tags.json")
        tags_data = {}
        if os.path.exists(tags_path):
            try:
                with open(tags_path, 'r') as f: tags_data = json.load(f)
            except: pass

        tabs = st.tabs(["🎞️ Master Cut (Complete)", "🔒 Product Highlights", "🔒 Funny Moments", "🔒 General Content", "🔒 Architecture Map", "🔒 Learning Log"])
        
        # MASTER VIDEO TAB (First & Default)
        with tabs[0]:
            st.subheader("🎞️ The Master Cut")
            st.markdown("**This is your complete video.** It contains all the kept clips (Product + Funny + General) in temporal order.")
            
            # Standardized Master Video Path
            master_path = os.path.join(OUTPUT_VIDEOS_DIR, "final_output_master_raw.mp4")

            if os.path.exists(master_path):
                st.success(f"📦 Master Video Ready ({os.path.getsize(master_path) / (1024*1024):.1f} MB)")
                st.video(master_path)
                with open(master_path, "rb") as f:
                     st.download_button("⬇️ Download Master Video", f, file_name="final_output_master_raw.mp4", key="dl_master")
            else:
                st.info("Master video not generated yet.")

        # LOCKED TABS
        for i in range(1, 6):
            with tabs[i]:
                st.info("🔒 This feature is available in the Premium Studio edition.")
                st.caption("Upgrade to unlock granular category breakdowns, architecture visualization, and autonomous learning logs.")

    # Main Area: File Upload
    # Check for chunks in input_clips (not yet started) OR processing (in progress)
    segments_in_input = []
    if os.path.exists(INPUT_CLIPS_DIR):
        segments_in_input = [f for f in os.listdir(INPUT_CLIPS_DIR) if f.startswith("segment_") and f.endswith(".mp4")]
        
    chunks_in_processing = []
    if os.path.exists(PROCESSING_DIR):
        chunks_in_processing = [f for f in os.listdir(PROCESSING_DIR) if f.startswith("segment_") and os.path.isdir(os.path.join(PROCESSING_DIR, f))]

    total_units_found = len(segments_in_input) + len(chunks_in_processing)

    if total_units_found > 0:
        st.warning(f"⚠️ Found {total_units_found} units from a previous session.")

        col1, col2 = st.columns([1, 2])
        with col1:
             if st.button("▶️ Resume Processing", type="primary"):
                st.divider()
                progress_bar = st.progress(0)
                status_text = st.empty()
                with st.status("🚀 Resuming Pipeline...", expanded=True) as status:
                    context = {"step_count": 0, "total_steps": total_units_found * 7}
                    
                    log_container = st.container(height=400)
                    
                    def ui_logger(message):
                        allowed_emojis = ["🚀", "✂️", "🏃", "🗣️", "👤", "🔒", "🕵️", "🎞️", "✨", "📥", "❌", "🛑", "⏩"]
                        is_headline = any(e in message for e in allowed_emojis)
                        is_success = "✅" in message
                        is_moved = "Moved" in message
                        is_noise = any(x in message for x in ["->", "Loading", "Scanning", "Using cache", "GL version"])
                        
                        if (is_headline or is_success or is_moved) and not is_noise:
                            with log_container:
                                st.write(message)
                            
                            if "✅" in message and "finished" in message:
                                context["step_count"] += 1
                                if context["total_steps"] > 0:
                                    progress_bar.progress(min(context["step_count"] / context["total_steps"], 1.0))
                            if is_headline and "finished" not in message:
                                clean = message.strip().replace("=", "").strip()
                                if clean: status.update(label=clean, state="running")

                    # Run pipeline directly with USER_ID
                    run_pipeline.main(logger_callback=ui_logger, user_id=user_id)
                    status.update(label="✨ Resume Completed!", state="complete", expanded=False)
                    progress_bar.progress(1.0)
                    st.success("🎉 Resume Complete! Check output below.")
                    
                    # CALL MERGE HERE
                    merge_and_display_result("resumed_output")
        
        with col2:
            if st.button("🗑️ Clear & Start New"):
                # Clear input segments
                for c in segments_in_input:
                    try: os.remove(os.path.join(INPUT_CLIPS_DIR, c))

                    except: pass
                # Clear processing chunks - AND OUTPUTS
                for c in chunks_in_processing:
                    try: shutil.rmtree(os.path.join(PROCESSING_DIR, c))
                    except: pass
                
                # Also clear state for this user?
                # state_manager.get_manager(user_id).clear_state()? 
                # Currently state is file based in data/state_{user}.json. We should delete that too?
                state_file = os.path.join(BASE_DIR, "data", f"state_{user_id}.json")
                if os.path.exists(state_file):
                    os.remove(state_file)
                st.rerun()

    # --- PERSISTENT REVIEW DASHBOARD ---
    if os.path.exists(FINAL_OUTPUT_DIR):
        merge_and_display_result("latest_run")
    # -----------------------------------
                
    uploaded_file = st.file_uploader("Upload a Video (.mp4)", type=["mp4"])
    
    if uploaded_file is not None:
        # Save uploaded file to input_clips
        file_path = os.path.join(INPUT_CLIPS_DIR, uploaded_file.name)
        with open(file_path, "wb") as f:
             while True:
                 chunk = uploaded_file.read(4 * 1024 * 1024) # 4MB chunks
                 if not chunk:
                     break
                 f.write(chunk)
        st.success(f"✅ Uploaded to workspace ({user_id}): {uploaded_file.name}")
        
        if st.button("🚀 Run AI Pipeline"):
            st.divider()
            
            # Progress bar
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # Use a container for the logs
            with st.status("🚀 Processing...", expanded=True) as status:
                
                # Callback to update UI logs
                context = {"step_count": 0, "total_steps": 1} # Dynamic
                
                def ui_logger(message):
                    # Strict Filter: Only allow Headlines and Important Code Blocks
                    allowed_emojis = ["🚀", "✂️", "🏃", "🗣️", "👤", "🔒", "🕵️", "🎞️", "✨", "📥", "❌", "🛑", "⏩"]
                    
                    is_headline = any(e in message for e in allowed_emojis)
                    is_success = "✅" in message
                    is_moved = "Moved" in message and "files" in message
                    
                    # Exclude specific noisy patterns
                    is_noise = any(x in message for x in ["->", "Loading", "Scanning", "Analyzing", "Using cache", "GL version", "TensorFlow"])
                    
                    if (is_headline or is_success or is_moved) and not is_noise:
                        st.write(message) 
                        
                        if "✅" in message and "finished" in message:
                            context["step_count"] += 1
                            if context["total_steps"] > 0:
                                progress = min(context["step_count"] / context["total_steps"], 1.0)
                                progress_bar.progress(progress)
                        
                        if is_headline and "finished" not in message:
                            clean_label = message.strip().replace("=", "").strip()
                            if clean_label:
                                status.update(label=clean_label, state="running")

                # --- STEP 1: SPLIT INTO CHUNKS (5 Minutes) ---
                st.write("🔪 Splitting into 5-minute chunks for stability...")
                
                # Temp dir for chunks
                chunk_output_pattern = os.path.join(INPUT_CLIPS_DIR, "segment_%04d.mp4")


                
                # FFmpeg Split Command
                cmd = [
                    "ffmpeg", "-y", "-i", file_path, 
                    "-c", "copy", "-map", "0", 
                    "-f", "segment", "-segment_time", "300", 
                    "-reset_timestamps", "1", 
                    chunk_output_pattern
                ]
                
                try:
                    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    st.write("✅ Splitting complete.")
                except subprocess.CalledProcessError as e:
                    st.error(f"❌ Splitting failed: {e}")
                    status.update(label="❌ Stopped", state="error")
                    return

                # Remove original large file
                if os.path.exists(file_path):
                    os.remove(file_path)

                # Count segments
                segments = [f for f in os.listdir(INPUT_CLIPS_DIR) if f.startswith("segment_") and f.endswith(".mp4")]
                segments.sort()
                
                if not segments:
                    st.error("❌ No segments created.")
                    return
                
                st.write(f"📦 Found {len(segments)} segments to process.")
                context["total_steps"] = len(segments) * 7 
                
                # --- STEP 2: RUN PIPELINE ON CHUNKS ---
                # Pass User ID here!
                run_pipeline.main(logger_callback=ui_logger, user_id=user_id)
                
                # Finalize
                status.update(label="✨ Pipeline Completed!", state="complete", expanded=False)
                progress_bar.progress(1.0)
            
            st.success("🎉 Processing Complete!")
            
            # CALL MERGE HERE
            file_stem = os.path.splitext(uploaded_file.name)[0]
            merge_and_display_result(file_stem)

if __name__ == "__main__":
    main()
