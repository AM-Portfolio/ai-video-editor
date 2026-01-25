import os
import shutil
import sys

def reset():
    print("🧹 Starting AI Video Pipeline Reset...")
    
    # Paths to clear
    dirs_to_clear = ["processing", "output_clips", "output_videos"]
    files_to_delete = ["data/pipeline_state.json"]
    
    # 1. Clear Directories
    for d in dirs_to_clear:
        if os.path.exists(d):
            print(f"   - Removing directory: {d}")
            shutil.rmtree(d)
        
        # Recreate empty directory
        os.makedirs(d, exist_ok=True)
        print(f"   - Recreated empty: {d}")

    # 2. Delete State File
    for f in files_to_delete:
        if os.path.exists(f):
            print(f"   - Deleting state file: {f}")
            os.remove(f)

    print("\n✅ Pipeline has been reset to a clean state.")
    print("🚀 You can now run 'python run_pipeline.py' for a fresh start.")

if __name__ == "__main__":
    # Prompt for confirmation unless -y is passed
    if "-y" not in sys.argv:
        confirm = input("⚠️ This will delete ALL processed data and output videos. Are you sure? (y/n): ")
        if confirm.lower() != 'y':
            print("❌ Reset cancelled.")
            sys.exit(0)
    
    reset()
