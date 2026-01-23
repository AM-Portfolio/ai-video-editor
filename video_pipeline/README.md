# 🎥 AI-Powered Video Editor Pipeline

**An intelligent, automated video editing engine that uses Computer Vision and Audio AI to transform raw footage into polished content.**

This project employs a multi-stage AI pipeline to autonomously detect the best moments in your video. By combining **Silero VAD (Neural Speech Detection)** and **MediaPipe (Face Analysis)**, it eliminates silence, removes bad takes, and ensures the subject is always in focus—all without manual intervention.

## 🧠 Key AI Technologies

### 1. Neural Voice Activity Detection (VAD)
Uses **Silero VAD**, a pre-trained deep learning model, to distinguish human speech from background noise, breathing, and silence with high precision. Unlike simple decibel-based cutting, this understands *voice*.

### 2. Computer Vision Face Tracking
Leverages **Google MediaPipe** to analyze every frame. The pipeline ensures:
*   **Presence**: The speaker is actually visible in the frame.
*   **Engagement**: Discards clips where the subject turns away or is obstructed.

### 3. Intelligent Privacy & Focus
Implements heuristic AI to identify the **Active Speaker** based on frame composition and size. Automatically detects and blurs bystander faces to maintain privacy and keep viewer attention on the main subject.

## 🚀 Quick Start

1.  **Drop Files**: Place your raw `.mp4` files into the `input_clips/` folder.
    *   *Note: Files must have an audio track.*
2.  **Run Pipeline**:
    ```bash
    python3 run_pipeline.py
    ```
3.  **Get Output**: Find your finished video in `output_clips/final_<filename>.mp4`.
    *   *Debug*: If enabled, check `output_clips/debug_<filename>.mp4` to see what was cut.

---

## ⚙️ Configuration (`config.json`)

Customize the behavior by editing `config.json`:

| Parameter | Default | Description |
| :--- | :--- | :--- |
| `debug_mode` | `true` | If `true`, generates an "X-ray" video showing accepted/rejected chunks. |
| `min_chunk_duration` | `1.5` | Minimum length (in seconds) for a clip to be kept. |
| `max_chunk_duration` | `15.0` | Maximum length before a long clip is forced split. |
| `silence_db` | `-30dB` | Audio threshold to consider as silence (lower = fewer splits). |
| `silence_duration` | `0.4` | Minimum silence length to trigger a split. |
| `motion_threshold` | `30000` | Sensitivity for removing static/idle frames (higher = less sensitive). |
| `face_confidence` | `0.5` | Confidence threshold (0.0 - 1.0) for detecting a face. |
| `crossfade_duration` | `0.1` | Duration (seconds) of the audio/video crossfade between clips. |

---

## 🛠 Pipeline Steps

The `run_pipeline.py` script automatically orchestrates these steps:

1.  **✂️ Smart Splitting**: Intelligently cuts video at natural pauses (silence).
2.  **🏃 Motion Filtering**: Removes segments where there is no movement (idle).
3.  **🗣️ VAD Filtering**: Uses Machine Learning to remove segments with no human speech.
4.  **👤 Face Detection**: Ensures the speaker is visible in the frame.
5.  **🔒 Privacy Blur**: (Optional) Blurs other faces or regions for privacy.
6.  **🕵️ Debug Visualization**: (Optional) Renders a timeline of all decisions.
7.  **🎞️ Final Merge**: Crossfades valid clips and normalizes audio to EBU R128 standards.

## 📂 Folder Structure

- `input_clips/`: Drop raw footage here.
- `processing/`: Intermediate working files (cleared automatically).
- `output_clips/`: Final and debug video outputs.
- `run_pipeline.py`: Main execution script.

---

## ⚠️ Troubleshooting

- **"No chunks to merge"**: The pipeline rejected everything. Check:
    - Does your video have audio? (VAD rejects silent files).
    - Is your microphone working? (Check volume levels).
    - Is your face visible? (Face detection requires good lighting).
- **Audio Error**: Ensure `ffmpeg` is installed and supports `loudnorm`.
