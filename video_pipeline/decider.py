import json
import os
from decision_log import DecisionLog
from score_keeper import ScoreKeeper

class Decider:
    def __init__(self, config_path="config.json"):
        self.logger = DecisionLog()
        self.scorer = ScoreKeeper()
        self.config = self._load_config(config_path)
        
    def _load_config(self, path):
        try:
            with open(path) as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

    def decide_clips(self, scores_path="processing/scores.json"):
        """
        Returns list of decision objects per clip.
        Reads scores from the provided path (default: processing/scores.json).
        """
        if not os.path.exists(scores_path):
            print(f"⚠️ Scores file not found: {scores_path}")
            return []
            
        with open(scores_path, "r") as f:
            try:
                all_scores = json.load(f)
            except json.JSONDecodeError:
                print(f"⚠️ Invalid JSON in scores file")
                return []
                
        # Load Semantic Tags
        semantic_path = "processing/semantic_tags.json"
        semantic_tags = {}
        if os.path.exists(semantic_path):
            with open(semantic_path) as f:
                semantic_tags = json.load(f)
                
        decider_config = self.config.get("decider", {})
        semantic_config = self.config.get("semantic_policy", {})
        semantic_weights_cfg = semantic_config.get("weights", {})
        semantic_default = semantic_config.get("default_weight", 0.5)

        keep_threshold = decider_config.get("keep_threshold", 0.65)
        weights = decider_config.get("weights", {
            "face": 0.4,
            "motion": 0.3,
            "speech": 0.3
        })
        
        decisions = []
        
        print(f"⚖️  Decider running (Threshold: {keep_threshold}, Semantic Adjusted)...")
        
        for clip_id, metrics in all_scores.items():
            # Extract scores, defaulting to 0.0 if missing
            face_score = metrics.get("face_score", 0.0)
            motion_score = metrics.get("motion_score", 0.0)
            vad_score = metrics.get("vad_score", 0.0)
            
            # Privacy penalty
            privacy_penalty = 0.0 
            
            # Base Quality Score
            quality_score = (
                weights.get("face", 0.0) * face_score +
                weights.get("motion", 0.0) * motion_score +
                weights.get("speech", 0.0) * vad_score
            )
            
            # Semantic Adjustment
            tag_data = semantic_tags.get(clip_id, {})
            tag = tag_data.get("category", "unknown")
            # If tag is unknown/missing, use default weight?
            # Or if checking tags.json failed, assume neutral?
            # Config has "default_weight".
            semantic_weight = semantic_weights_cfg.get(tag, semantic_default)
            if tag == "unknown":
                 # If we didn't run semantic tagger, or it skipped this clip (low quality),
                 # we should trust the default. 
                 # If semantic tagger skipped it, it likely had low quality anyway.
                 pass

            final_score = quality_score * semantic_weight * (1.0 - privacy_penalty)
            
            # Decision
            decision_enum = "keep" if final_score >= keep_threshold else "discard"
            
            # Top Factors
            # We treat Semantic Weight as a factor relative to 1.0?
            factors = [
                ("Face Visibility", face_score * weights.get("face", 0.0)),
                ("Motion", motion_score * weights.get("motion", 0.0)),
                ("Speech", vad_score * weights.get("speech", 0.0)),
                (f"Topic: {tag}", (semantic_weight - 0.5) if semantic_weight != 1.0 else 0.1) 
                # Semantic factor visualization is tricky. 
                # If weight is 1.0, it doesn't "add", it "preserves".
                # If weight is 0.2, it "removes". 
                # Let's just list it if it's significant (high or low).
            ]
            
            # Simplified factor sorting for display
            factors.sort(key=lambda x: x[1], reverse=True)
            top_factors = [f[0] for f in factors[:3] if f[1] > 0] # Top 3 now
            
            # Construct Result Object
            result = {
                "clip_id": clip_id,
                "final_score": round(final_score, 3),
                "decision": decision_enum,
                "confidence": round(final_score, 3), 
                "top_factors": top_factors,
                "semantic_category": tag,
                "semantic_weight": semantic_weight
            }
            decisions.append(result)
            
            # Log It
            self.logger.log(
                module="decider",
                decision=decision_enum,
                confidence=result["confidence"],
                reason="weighted_score_semantic",
                metrics={
                    "final_score": result["final_score"],
                    "quality_score": round(quality_score, 3),
                    "semantic_category": tag,
                    "semantic_weight": semantic_weight,
                    "raw_inputs": metrics,
                    "weights": weights
                }
            )
            
            icon = "✅" if decision_enum == "keep" else "❌"
            tag_str = f"[{tag.upper()}]" if tag != "unknown" else ""
            print(f"   {icon} {clip_id}: {final_score:.2f} {tag_str} -> {decision_enum.upper()}")
            
        # Save Decisions for downstream steps
        decisions_path = "processing/decisions.json"
        with open(decisions_path, "w") as f:
            json.dump(decisions, f, indent=2)
            
        return decisions

if __name__ == "__main__":
    # Standalone run
    decider = Decider()
    decider.decide_clips()
