import json
import os
import sys
# Add project root to sys.path for modular imports
sys.path.append(os.getcwd())
import shutil
import datetime

from core.logging import DecisionLog
import fcntl

class ActionExecutor:
    def __init__(self, log_file="processing/action_log.json"):
        self.log_file = log_file
        self.base_processing_dir = "processing" 
        # We need to look into subfolders since filters moved them around.
        # But Phase 2 normalized everything to:
        # - keep/speech (if VAD ran)
        # - keep (if motion ran)
        # Essentially deep search? Or just robust find.
        
    def _find_clip_path(self, clip_filename):
        """
        Locate the clip within the processing structure.
        Recursively searches 'processing' directory.
        """
        for root, dirs, files in os.walk(self.base_processing_dir):
            if clip_filename in files:
                return os.path.join(root, clip_filename)
        return None

    def execute_plan(self, plan):
        """
        Executes the list of actions.
        """
        print(f"🚜 Executing {len(plan)} actions...")
        
        executed_count = 0
        
        for item in plan:
            clip_id = item["clip_id"] # This is usually the filename e.g. "chunk_001.mp4"
            action = item["action"]
            dest_folder = item["destination"]
            
            # 1. Locate Source
            src_path = self._find_clip_path(clip_id)
            if not src_path:
                print(f"   ⚠️ Could not find source file for {clip_id}. Skipping.")
                continue
                
            # 2. Prepare Destination
            os.makedirs(dest_folder, exist_ok=True)
            dst_path = os.path.join(dest_folder, clip_id)
            
            # 3. Execute Move/Copy
            try:
                # We use copy to preserve processing state for debugging? 
                # Or move to clean up? 
                # "Action: keep" usually implies moving to output.
                # "Action: discard" -> move to discard folder? 
                # Prompt said "Actions can be: keep, discard, quarantine".
                # And "Moves files".
                # I'll use move, or copy if we want to keep processing intact.
                # Usually final export copies.
                # But to avoid disk usage explosion, maybe move?
                # Let's COPY for safety, so 'processing' remains a valid audit trail until cleared.
                shutil.copy2(src_path, dst_path)
                
                # 4. Log Action
                self._log_action(clip_id, action, dest_folder)
                executed_count += 1
                
            except Exception as e:
                print(f"   ❌ Failed to execute action for {clip_id}: {e}")
                
        print(f"✅ Executed {executed_count}/{len(plan)} actions.")

    def _log_action(self, clip_id, action, destination):
        entry = {
            "clip_id": clip_id,
            "action": action,
            "destination": destination,
            "executed_at": datetime.datetime.now().isoformat()
        }
        
        # File lock append
        try:
            with open(self.log_file, "a") as f:
                fcntl.flock(f, fcntl.LOCK_EX)
                try:
                    f.write(json.dumps(entry) + "\n")
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)
        except Exception as e:
            print(f"   ⚠️ Failed to log action: {e}")

if __name__ == "__main__":
    executor = ActionExecutor()
    plan_path = "processing/action_plan.json"
    
    if os.path.exists(plan_path):
        with open(plan_path, "r") as f:
            plan = json.load(f)
        executor.execute_plan(plan)
    else:
        print("⚠️ No action plan found to execute.")
