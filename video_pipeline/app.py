import streamlit as st
import os
import json
import threading
from queue import Queue
import time
import shutil
import sys
# Add project root to sys.path for modular imports
sys.path.append(os.getcwd())

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
        "enabled": False,
        "weights": {"product_related": 1.0, "funny": 1.0, "general": 0.9}
    },
    "self_learning": True,
    "b_roll": {"enabled": False}
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
    # CRITICAL: Set Env Var so path_utils knows who we are!
    os.environ["PIPELINE_USER_ID"] = user_id
    
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

    # Smart B-Roll Toggle (New)
    enable_broll = st.sidebar.checkbox(
        "Enable Smart B-Roll (Generative AI)", config.get("b_roll", {}).get("enabled", False),
        help="Automatically generates AI images for high-scoring visual moments in your video."
    )

    # Logic: B-Roll requires LLM
    llm_default = config.get("semantic_policy", {}).get("enabled", False)
    if enable_broll:
        llm_default = True
        st.sidebar.info("🧠 LLM Labeling auto-enabled for B-Roll analysis.")
    
    enable_llm = st.sidebar.checkbox(
        "Enable LLM Labeling", llm_default,
        disabled=enable_broll, # Lock if B-Roll is on
        help="**Uncheck (Default)**: Creates a fast 'Master Cut' based on motion/faces only.\n**Check**: Uses AI to categorize clips (Product vs Funny) and analyze Visual Potential."
    )
    
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
        
        if "semantic_policy" not in config: config["semantic_policy"] = {}
        config["semantic_policy"]["enabled"] = enable_llm
        config["semantic_policy"]["weights"] = {"product_related": s_product, "funny": s_funny, "general": s_general}

        if "b_roll" not in config: config["b_roll"] = {}
        config["b_roll"]["enabled"] = enable_broll
        
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
            
            # Standardized Master Video Path (Prefer Smart B-Roll version)
            smart_path = os.path.join(OUTPUT_VIDEOS_DIR, "final_video_smart.mp4")
            raw_path = os.path.join(OUTPUT_VIDEOS_DIR, "final_output_master_raw.mp4")
            
            final_path = smart_path if os.path.exists(smart_path) else raw_path

            if os.path.exists(final_path):
                st.success(f"📦 Master Video Ready ({os.path.getsize(final_path) / (1024*1024):.1f} MB)")
                
                # Layout: Video | Thumbnail
                col_vid, col_thumb = st.columns([2, 1])
                
                with col_vid:
                    st.video(final_path)
                    with open(final_path, "rb") as f:
                         st.download_button("⬇️ Download Video", f, file_name=os.path.basename(final_path), key=f"dl_master_{base_name}")

                with col_thumb:
                    thumb_path = os.path.join(OUTPUT_VIDEOS_DIR, "thumbnail.png")
                    if os.path.exists(thumb_path):
                    if os.path.exists(thumb_path):
                        st.image(thumb_path, caption="🎨 Generated YouTube Thumbnail", width="stretch") # Updated API
                        with open(thumb_path, "rb") as f:
                             st.download_button("⬇️ Download Thumbnail", f, file_name="thumbnail.png", mime="image/png", key=f"dl_thumb_{base_name}")
                    else:
                        st.info("Generating thumbnail... (If enabled)")
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
        segments_in_input = [f for f in os.listdir(INPUT_CLIPS_DIR) if f.endswith(".mp4")]
        
    chunks_in_processing = []
    if os.path.exists(PROCESSING_DIR):
        # Scan for ANY subdirectory that might contain chunks (e.g. video name folders)
        # Exclude 'b_roll' or other artifacts folder if possible, but generally any folder suggests work in progress
        chunks_in_processing = [f for f in os.listdir(PROCESSING_DIR) if os.path.isdir(os.path.join(PROCESSING_DIR, f)) and f != "b_roll"]

    total_units_found = len(segments_in_input) + len(chunks_in_processing)

    if total_units_found > 0:
        st.warning(f"⚠️ Found {total_units_found} units from a previous session.")

        col1, col2 = st.columns([1, 2])
        with col1:
             if st.button("▶️ Resume Processing", type="primary"):
                st.session_state["pipeline_active"] = True
                st.session_state["pipeline_step"] = 0 # Resume usually implies ingest is done
                st.session_state["pipeline_logs"] = ["🚀 Resuming Pipeline..."]
                st.session_state["pipeline_stem"] = "resumed_video"
                st.rerun()
        
        with col2:
            if st.button("🗑️ Clear & Start New"):
                for c in segments_in_input:
                    try: os.remove(os.path.join(INPUT_CLIPS_DIR, c))
                    except: pass
                for c in chunks_in_processing:
                    try: shutil.rmtree(os.path.join(PROCESSING_DIR, c))
                    except: pass
                
                state_file = os.path.join(BASE_DIR, "data", f"state_{user_id}.json")
                if os.path.exists(state_file):
                    os.remove(state_file)
                st.rerun()
    
    # --- PERSISTENT REVIEW DASHBOARD ---
    if os.path.exists(FINAL_OUTPUT_DIR):
        merge_and_display_result("latest_run")
    # -----------------------------------
    
    uploaded_file = None
    if total_units_found == 0:
        uploaded_file = st.file_uploader("Upload a Video (.mp4)", type=["mp4"])
    
    if uploaded_file is not None:
        file_path = os.path.join(INPUT_CLIPS_DIR, uploaded_file.name)
        with open(file_path, "wb") as f:
             while True:
                 chunk = uploaded_file.read(4 * 1024 * 1024)
                 if not chunk: break
                 f.write(chunk)
        st.success(f"✅ Uploaded to workspace ({user_id}): {uploaded_file.name}")
        
        if st.button("🚀 Run AI Pipeline"):
             # FORCE RESET STATE on new run
             state_file = os.path.join(BASE_DIR, "data", f"state_{user_id}.json")
             if os.path.exists(state_file):
                 try: os.remove(state_file)
                 except: pass

             st.session_state["pipeline_active"] = True
             st.session_state["pipeline_step"] = -1
             st.session_state["pipeline_logs"] = ["🚀 Starting New Run..."]
             st.session_state["pipeline_stem"] = os.path.splitext(uploaded_file.name)[0]
             st.rerun()

    # ==========================================
    # 🚀 SHARED PIPELINE RUNNER (State Machine)
    # ==========================================
    if st.session_state.get("pipeline_active", False):
        st.divider()
        st.subheader("⚙️ Processing Engine")
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        col_stop, _ = st.columns([1, 4])
        with col_stop:
            if st.button("🛑 STOP PIPELINE", type="primary"):
                st.session_state["pipeline_active"] = False
                st.session_state["pipeline_logs"].append("🛑 Pipeline Stopped by User.")
                st.error("🛑 Pipeline Stopped.")
                st.stop()
        
        with st.container(height=400):
            for log in st.session_state.get("pipeline_logs", []):
                st.write(log)
        
        def add_log(msg):
            st.session_state["pipeline_logs"].append(msg)
            print(msg)

        current_step = st.session_state.get("pipeline_step", 0)
        steps = run_pipeline.STEPS
        
        # STEP -1: SPLITTING
        if current_step == -1:
            add_log("🔪 Step 1: Ingest...")
            run_pipeline.ingest_files(logger_callback=None)
            st.session_state["pipeline_step"] = 0
            st.rerun()

        # STEPS 0...N
        elif 0 <= current_step < len(steps):
            step_name, step_script = steps[current_step]
            
            progress = current_step / len(steps)
            progress_bar.progress(progress)
            status_text.text(f"Running: {step_name}")
            
            add_log(f"▶️  Running: {step_name}")
            
            success = run_pipeline.run_step(step_name, step_script, logger_callback=add_log)
            
            if not success:
               add_log(f"❌ Failed at {step_name}")
               st.session_state["pipeline_active"] = False
               st.error(f"Pipeline failed at {step_name}")
               # st.stop() # Allow viewing logs
            
            st.session_state["pipeline_step"] += 1
            st.rerun()
            
        # DONE
        elif current_step >= len(steps):
            progress_bar.progress(1.0)
            status_text.text("✨ Complete!")
            st.balloons()
            st.success("🎉 Pipeline Finished Successfully!")
            
            stem = st.session_state.get("pipeline_stem", "video")
            merge_and_display_result(stem)
            
            if st.button("✅ Done (Reset View)"):
                st.session_state["pipeline_active"] = False
                st.rerun()

if __name__ == "__main__":
    main()
