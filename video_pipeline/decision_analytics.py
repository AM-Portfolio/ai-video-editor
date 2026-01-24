import json
import os
import math
from collections import Counter

class DecisionAnalytics:
    def __init__(self, config_path="config.json"):
        self.scores_path = "processing/scores.json"
        self.log_path = "processing/decision_log.json"
        self.summary_path = "processing/run_summary.json"
        self.config = self._load_config(config_path)

    def _load_config(self, path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            return {}

    def analyze_run(self):
        print("📊 Running Decision Analytics...")
        
        if not os.path.exists(self.scores_path):
            print(f"⚠️ Scores file not found: {self.scores_path}")
            return {}

        with open(self.scores_path, "r") as f:
            try:
                scores = json.load(f)
            except json.JSONDecodeError:
                return {}

        # Get Config Parameters
        decider_config = self.config.get("decider", {})
        threshold = decider_config.get("keep_threshold", 0.65)
        weights = decider_config.get("weights", {"face": 0.4, "motion": 0.3, "speech": 0.3})
        
        # 1. Aggregate Stats
        total_clips = len(scores)
        kept_clips = 0
        final_scores = []
        decisions = []
        
        # 2. Rejection Analysis Containers
        rejection_reasons = []
        
        # 3. Sensitivity Containers
        borderline_count = 0
        borderline_range = 0.05
        
        for clip_id, metrics in scores.items():
            # Re-compute final score to ensure consistency
            face = metrics.get("face_score", 0.0)
            motion = metrics.get("motion_score", 0.0)
            speech = metrics.get("vad_score", 0.0)
            
            # Valid factors for this clip
            w_face = weights.get("face", 0.0)
            w_motion = weights.get("motion", 0.0)
            w_speech = weights.get("speech", 0.0)
            
            raw_score = (w_face * face) + (w_motion * motion) + (w_speech * speech)
            # Assuming privacy penalty is 0 for now as per Decider implementation
            final_score = raw_score 
            
            final_scores.append(final_score)
            
            is_kept = final_score >= threshold
            if is_kept:
                kept_clips += 1
            
            decisions.append({
                "clip_id": clip_id,
                "score": final_score,
                "decision": "keep" if is_kept else "discard"
            })
            
            # Rejection Reason Analysis
            if not is_kept:
                # Find lowest contributing factor relative to max possible contribution?
                # Or just lowest weighted score? 
                # "Lowest contributing score" = min(w * score)
                # This highlights what pulled the score down.
                contributions = {
                    "poor_face_visibility": w_face * face,
                    "unstable_motion": w_motion * motion, # motion score is low if static? "unstable" name might be confusing if motion filter checks distinctness. 
                    # If motion filter removes static scenes, low score = static. So "static_scene" is better.
                    # But prompt example used "unstable_motion". I will use "low_motion_interest".
                    "low_motion_interest": w_motion * motion,
                    "low_speech": w_speech * speech
                }
                # Find min
                reason = min(contributions, key=contributions.get)
                rejection_reasons.append(reason)
                
            # Sensitivity Analysis
            dist_to_threshold = abs(final_score - threshold)
            if dist_to_threshold <= borderline_range:
                borderline_count += 1

        # Compute aggregates
        discarded_clips = total_clips - kept_clips
        keep_rate = discarded_clips # Wait, rate is ratio
        keep_rate = kept_clips / total_clips if total_clips > 0 else 0.0
        avg_score = sum(final_scores) / total_clips if total_clips > 0 else 0.0
        
        # Distribution
        dist_buckets = {
            "0.0-0.3": 0,
            "0.3-0.6": 0,
            "0.6-1.0": 0
        }
        for s in final_scores:
            if s < 0.3: dist_buckets["0.0-0.3"] += 1
            elif s < 0.6: dist_buckets["0.3-0.6"] += 1
            else: dist_buckets["0.6-1.0"] += 1

        # Top Rejection Reasons
        top_rejections = dict(Counter(rejection_reasons).most_common(3))
        
        # Build Report
        report = {
            "overview": {
                "total_clips": total_clips,
                "kept": kept_clips,
                "discarded": discarded_clips,
                "keep_rate": round(keep_rate, 2),
                "avg_final_score": round(avg_score, 2),
                "threshold_used": threshold
            },
            "score_distribution": dist_buckets,
            "quality_insights": {
                "top_rejection_reasons": top_rejections,
                "borderline_clips": borderline_count,
                 # Identify most sensitive weights (just identifying the heaviest weights)
                "dominant_weights": sorted(weights.keys(), key=lambda k: weights[k], reverse=True)
            },
            "config_snapshot": decider_config
        }
        
        # Save Report
        with open(self.summary_path, "w") as f:
            json.dump(report, f, indent=2)
            
        print(f"✅ Analysis Complete.")
        print(f"   Kept: {kept_clips}/{total_clips} ({keep_rate:.1%})")
        print(f"   Avg Score: {avg_score:.2f}")
        print(f"   Borderline: {borderline_count}")
        print(f"   Report saved to: {self.summary_path}")
        
        return report

if __name__ == "__main__":
    analytics = DecisionAnalytics()
    analytics.analyze_run()
