import json
import os
import sys

# Add project root to sys.path for modular imports
sys.path.append(os.getcwd())

from core import path_utils

class ActionPlanner:
    def __init__(self, config_path="config.json"):
        self.config = self._load_config(config_path)

    def _load_config(self, path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            return {}

    def plan_actions(self, decisions):
        """
        Translates soft decisions (scores) into hard actions (keep/discard/quarantine).
        Input: List of decision objects from Decider.
        Output: List of action plans.
        """
        policy = self.config.get("action_policy", {})
        confident_keep_thresh = policy.get("confident_keep", 0.75)
        borderline_thresh = policy.get("borderline", 0.6)
        
        plan = []
        
        print("🗺️  Planning Actions...")
        
        for d in decisions:
            clip_id = d.get("clip_id")
            score = d.get("confidence", 0.0) # Using confidence/final_score
            
            # Determine User ID for path segregation
            user_id = path_utils.get_user_id()
            output_root = path_utils.get_output_clips_dir()
            
            # Default action
            action = "discard"
            destination = os.path.join(output_root, "discarded")
            reason_suffix = ""
            
            # Determine Action based on Decider's explicit decision
            decision_raw = d.get("decision", "discard").lower()
            
            if decision_raw == "keep":
                action = "keep"
                # Categorize Output
                category = d.get("semantic_category", "general")
                # Normalize category folder name (e.g. product_related -> product_related)
                if category in ["product_related", "funny", "general"]:
                    destination = os.path.join(output_root, category)
                else:
                    destination = os.path.join(output_root, "selected")
            elif decision_raw == "quarantine":
                action = "quarantine"
                destination = os.path.join(output_root, "quarantine")
                reason_suffix = " (Borderline)"
            else:
                # Discard
                action = "discard"
                destination = os.path.join(output_root, "discarded")
            
            # Formulate human readable reason
            top_factors = d.get("top_factors", [])
            reason_str = ", ".join(top_factors) if top_factors else "low score"
            if reason_suffix:
                reason_str += reason_suffix
                
            plan_item = {
                "clip_id": clip_id,
                "action": action,
                "destination": destination,
                "reason": reason_str,
                "score": score # Pass score for context if needed
            }
            plan.append(plan_item)
            
            # Debug Print
            indicator = {
                "keep": "🟢",
                "quarantine": "🟡",
                "discard": "🔴"
            }.get(action, "⚪️")
            
            print(f"   {indicator} {clip_id} -> {action.upper()} ({reason_str})")
            
        return plan

if __name__ == "__main__":
    planner = ActionPlanner()
    proc_dir = path_utils.get_processing_dir()
    decisions_path = os.path.join(proc_dir, "decisions.json")
    plan_path = os.path.join(proc_dir, "action_plan.json")
    
    if os.path.exists(decisions_path):
        with open(decisions_path, "r") as f:
            decisions = json.load(f)
        
        plan = planner.plan_actions(decisions)
        
        with open(plan_path, "w") as f:
            json.dump(plan, f, indent=2)
        print(f"📝 Action Plan saved to {plan_path}")
    else:
        print("⚠️ No decisions found to plan.")
