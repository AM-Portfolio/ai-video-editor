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
    try:
        max_upload = st.config.get_option("server.maxUploadSize")
        st.sidebar.caption(f"Max Upload Size: {max_upload}MB")
    except:
        pass
    
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
    
    def merge_and_display_result(base_name="video"):
        # Check for output videos
        if os.path.exists(FINAL_OUTPUT_DIR):
            # Identify chunks that were processed
            chunk_finals = [f for f in os.listdir(FINAL_OUTPUT_DIR) if f.startswith("final_chunk_") and f.endswith(".mp4")]
            chunk_finals.sort()
            
            if chunk_finals:
                st.divider()
                
                # --- NEW: Individual Chunk Review ---
                st.subheader("📼 Review Individual Chunks")
                for i, chunk in enumerate(chunk_finals):
                    with st.expander(f"▶️ Play {chunk}", expanded=False):
                        chunk_path = os.path.join(FINAL_OUTPUT_DIR, chunk)
                        st.video(chunk_path)
                        # Placeholder for future feedback
                        st.text_area(f"Feedback for {chunk}", placeholder="Notes for this segment...", key=f"note_{i}")
                
                st.divider()
                st.write("🧩 Merging final segments...")
                
                # Create concat list for final merge
                concat_list_path = os.path.join(FINAL_OUTPUT_DIR, "concat_final_list.txt")
                with open(concat_list_path, "w") as f:
                    for chunk in chunk_finals:
                        abs_path = os.path.join(FINAL_OUTPUT_DIR, chunk).replace("\\", "/")
                        f.write(f"file '{abs_path}'\n")
                        
                # Final Output Name
                master_output = os.path.join(FINAL_OUTPUT_DIR, f"final_MASTER_{base_name}.mp4")
                
                cmd_merge = [
                    "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                    "-i", concat_list_path,
                    "-c", "copy",
                    master_output
                ]
                
                try:
                    subprocess.run(cmd_merge, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    st.subheader("🎞️ Final Result")
                    st.video(master_output)
                    
                    with open(master_output, "rb") as video_file:
                        st.download_button(
                            label="⬇️ Download Final Video",
                            data=video_file,
                            file_name=os.path.basename(master_output),
                            mime="video/mp4"
                        )
                        
                except subprocess.CalledProcessError as e:
                    st.error(f"❌ Final merge failed: {e}")
            else:
                st.warning("No output chunks found. Check logs for errors.")

    # Main Area: File Upload
    PROCESSING_DIR = os.path.join(BASE_DIR, "processing")
    
    # Check for chunks in input_clips (not yet started) OR processing (in progress)
    chunks_in_input = []
    if os.path.exists(INPUT_CLIPS_DIR):
        chunks_in_input = [f for f in os.listdir(INPUT_CLIPS_DIR) if f.startswith("chunk_") and f.endswith(".mp4")]
        
    chunks_in_processing = []
    if os.path.exists(PROCESSING_DIR):
        chunks_in_processing = [f for f in os.listdir(PROCESSING_DIR) if f.startswith("chunk_") and os.path.isdir(os.path.join(PROCESSING_DIR, f))]

    total_chunks_found = len(chunks_in_input) + len(chunks_in_processing)

    if total_chunks_found > 0:
        st.warning(f"⚠️ Found {total_chunks_found} chunks from a previous session ({len(chunks_in_processing)} in progress).")
        col1, col2 = st.columns([1, 2])
        with col1:
             if st.button("▶️ Resume Processing", type="primary"):
                st.divider()
                progress_bar = st.progress(0)
                status_text = st.empty()
                with st.status("🚀 Resuming Pipeline...", expanded=True) as status:
                    context = {"step_count": 0, "total_steps": total_chunks_found * 7}
                    
                    def ui_logger(message):
                        allowed_emojis = ["🚀", "✂️", "🏃", "🗣️", "👤", "🔒", "🕵️", "🎞️", "✨", "📥", "❌", "🛑", "⏩"]
                        is_headline = any(e in message for e in allowed_emojis)
                        is_success = "✅" in message
                        is_moved = "Moved" in message
                        is_noise = any(x in message for x in ["->", "Loading", "Scanning", "Using cache", "GL version"])
                        
                        if (is_headline or is_success or is_moved) and not is_noise:
                            st.write(message)
                            if "✅" in message and "finished" in message:
                                context["step_count"] += 1
                                if context["total_steps"] > 0:
                                    progress_bar.progress(min(context["step_count"] / context["total_steps"], 1.0))
                            if is_headline and "finished" not in message:
                                clean = message.strip().replace("=", "").strip()
                                if clean: status.update(label=clean, state="running")

                    # Run pipeline directly
                    run_pipeline.main(logger_callback=ui_logger)
                    status.update(label="✨ Resume Completed!", state="complete", expanded=False)
                    progress_bar.progress(1.0)
                    st.success("🎉 Resume Complete! Check output below.")
                    
                    # CALL MERGE HERE
                    merge_and_display_result("resumed_output")
        
        with col2:
            if st.button("🗑️ Clear & Start New"):
                # Clear input chunks
                for c in chunks_in_input:
                    try: os.remove(os.path.join(INPUT_CLIPS_DIR, c))
                    except: pass
                # Clear processing chunks - AND OUTPUTS
                for c in chunks_in_processing:
                    try: shutil.rmtree(os.path.join(PROCESSING_DIR, c))
                    except: pass
                
                # Also clear output clips if we are clearing everything?
                # Maybe safe to keep them, but "Clear & Start New" implies fresh start.
                # Let's clean outputs carefully or leave them. User might want to keep history.
                # Just keeping logic as is: clearing Inputs/Processing resets state.
                st.rerun()

    # --- PERSISTENT REVIEW DASHBOARD ---
    # Show this ALWAYS if output files exist, so user can see previous results immediately
    if os.path.exists(FINAL_OUTPUT_DIR):
        final_chunks = [f for f in os.listdir(FINAL_OUTPUT_DIR) if f.startswith("final_chunk_") and f.endswith(".mp4")]
        debug_chunks = [f for f in os.listdir(FINAL_OUTPUT_DIR) if f.startswith("debug_chunk_") and f.endswith(".mp4")]
        final_chunks.sort()
        debug_chunks.sort()
        
        if final_chunks or debug_chunks:
            st.divider()
            st.header("📼 Project Review")
            
            tab_final, tab_debug = st.tabs(["✨ Final Segments", "🕵️ Debug Visualization"])
            
            with tab_final:
                if final_chunks:
                    for chunk in final_chunks:
                        with st.expander(f"▶️ {chunk}", expanded=False):
                            st.video(os.path.join(FINAL_OUTPUT_DIR, chunk))
                else:
                    st.info("No final chunks yet.")
                    
            with tab_debug:
                if debug_chunks:
                    for chunk in debug_chunks:
                        with st.expander(f"▶️ {chunk}", expanded=False):
                            st.video(os.path.join(FINAL_OUTPUT_DIR, chunk))
                else:
                    st.info("No debug visualizations yet.")
            
            # Check for Master File
            master_files = [f for f in os.listdir(FINAL_OUTPUT_DIR) if f.startswith("final_MASTER_") and f.endswith(".mp4")]
            if master_files:
                st.subheader("🎉 Master Output")
                latest_master = max([os.path.join(FINAL_OUTPUT_DIR, f) for f in master_files], key=os.path.getctime)
                st.video(latest_master)
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
        st.success(f"✅ Uploaded: {uploaded_file.name}")
        
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
                            # Estimate depends on how many chunks we have
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
                chunk_output_pattern = os.path.join(INPUT_CLIPS_DIR, "chunk_%03d.mp4")
                
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

                # Count chunks
                chunks = [f for f in os.listdir(INPUT_CLIPS_DIR) if f.startswith("chunk_") and f.endswith(".mp4")]
                chunks.sort()
                
                if not chunks:
                    st.error("❌ No chunks created.")
                    return
                
                st.write(f"📦 Found {len(chunks)} chunks to process.")
                context["total_steps"] = len(chunks) * 7 
                
                # --- STEP 2: RUN PIPELINE ON CHUNKS ---
                run_pipeline.main(logger_callback=ui_logger)
                
                # Finalize
                status.update(label="✨ Pipeline Completed!", state="complete", expanded=False)
                progress_bar.progress(1.0)
            
            st.success("🎉 Processing Complete!")
            
            # CALL MERGE HERE
            file_stem = os.path.splitext(uploaded_file.name)[0]
            merge_and_display_result(file_stem)


if __name__ == "__main__":
    main()
