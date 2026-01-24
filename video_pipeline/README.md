# AI Video Editor Pipeline 🧠
> A Decision Intelligence System for automated video processing.

This project implements a professional-grade AI pipeline that transforms raw video footage into a polished edit using a sophisticated **Perception -> Decision -> Action** architecture.

## 🌟 Key Features

*   **Voice-First Decisions:** Prioritizes content (speech) over visuals. If you are talking clearly, the clip is kept even if you are looking away (`config.json`).
*   **Human-Supervised Knowledge Distillation:** Instead of blind learning, the AI proposes new search heuristics (Regex) after each run. You review and approve them in the dashboard to reduce future LLM costs without losing control.
*   **Infinite Resilience (Resume Everywhere):** Every step and every individual chunk is tracked. If the system crashes or you stop it, it resumes exactly where it left off, saving hours of processing time.
*   **Semantic Sorting:** Automatically routes clips into:
    *   `product_related` (Coding, Tech)
    *   `funny` (Jokes, Laughter)
    *   `general` (Life updates - kept if voice is clear)
*   **Centralized Decider**: A single "Brain" (`decider.py`) makes holistic decisions based on weighted scores and configurable logic.
*   **Explainable AI**: Every decision is traced, analyzed, and explained. The system produces a human-readable narrative and detailed per-clip justifications.

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
