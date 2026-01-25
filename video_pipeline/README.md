# AI Video Editor Pipeline 🧠
> A Decision Intelligence System for automated video processing.

This project implements a professional-grade AI pipeline that transforms raw video footage into a polished edit using a sophisticated **Perception -> Decision -> Action** architecture.

## 🌟 Key Features

*   **Context-Aware Intelligence:** The AI remembers conversation history (Sliding Window). If you laugh during a deep technical explanation, it now understands that laughter is `product_related`, not just generic `funny`.
*   **Voice-First Decisions:** Prioritizes content (speech) over visuals. High-Recall tuning ensures even quiet murmurs are captured (`-45dB` sensitivity).
*   **Human-Supervised Knowledge Distillation:** The AI learns from your content. It identifies new technical terms ("deploy", "merge", "stock market") and updates its own knowledge base (`knowledge.py`) to get smarter over time.
*   **Infinite Resilience (Resume Everywhere):** Every step and every individual chunk is tracked. Crashing is impossible to recover from; the system simply resumes.
*   **Master Video Generation:** Automatically merges all kept clips into a single resilient timeline (`final_output_master_raw.mp4`), in addition to categorized topic videos.
*   **Explainable AI:** Every decision is traced. Why was that clip dropped? The `clip_explanations.json` will tell you: "Low face visibility and no excitement."

## 🏗 Architecture

The pipeline operates in distinct phases:

1.  **Perception (Sensors)**
    *   `smart_splitter.py`: Chunks video.
    *   `motion_filter.py`: Scores visual interest.
    *   `vad_filter.py`: Scores speech quality.
    *   `face_filter.py`: Scores face visibility.
    *   `semantic_tagger.py`: Listens to speech (Whisper) + Classifies meaning (Together AI).

2.  **Intelligence (The Brain)**
    *   `decider.py`: Aggregates scores -> Makes decisions. Uses Priority Logic (Product > Funny > General).
    *   `decision_analytics.py`: Analyzes run statistics, rejects reasons, and sensitivity.

3.  **Policy & Action**
    *   `action_planner.py`: Translates decisions into a categorized plan based on content type.
    *   `action_executor.py`: Safely routes clips to `output_clips/product_related`, `funny`, etc.

4.  **Explanation (Trust)**
    *   `run_explainer.py`: Generates `run_summary.json` (Narrative) and `clip_explanations.json` (Detail).

5.  **Output**
    *   `merge_final.py`: Merges the categorized clips into final videos (`final_output_product_related.mp4`, etc).

## 🚀 Usage

```bash
# 1. Place raw videos in input_clips/
# 2. Run the full pipeline
python video_pipeline/run_pipeline.py
```

## ⚙️ Configuration

Control the brain via `video_pipeline/config.json`. The current policy is **Voice-Centric**:

```json
{
    "decider": {
        "keep_threshold": 0.50,
        "weights": {
            "face": 0.1,
            "motion": 0.2,
            "speech": 0.7  <-- High weight on Voice
        }
    },
    "semantic_policy": {
        "weights": {
            "product_related": 1.0,
            "funny": 1.0,
            "general": 0.9 <-- High weight to keep clear speech
        }
    }
}
```

## 📂 Output Structure

*   `input_clips/`: Drop raw footage here.
*   `output_clips/product_related`: Tech clips.
*   `output_clips/funny`: Funny clips.
*   `output_clips/general`: Vlog/Life clips.
*   `output_videos/`: Final merged videos (Ready to watch).
*   `processing/`: Intermediate artifacts (scores, logs).
