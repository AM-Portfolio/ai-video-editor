import os
import shutil
import sys

def reset():
    print("🧹 Starting AI Video Pipeline Reset...")
    
    # Paths to clear
    dirs_to_clear = ["input_clips", "processing", "output_clips", "output_videos"]
    files_to_delete = ["data/pipeline_state.json"]
    
    # 1. Clear Directories (Content only, preserve inodes for Docker)
    for d in dirs_to_clear:
        if os.path.exists(d):
            print(f"   - Clearing contents of: {d}")
            for item in os.listdir(d):
                item_path = os.path.join(d, item)
                try:
                    if os.path.isfile(item_path) or os.path.islink(item_path):
                        os.remove(item_path)
                    elif os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                except Exception as e:
                    print(f"     ⚠️ Failed to delete {item}: {e}")
        else:
            # Create if doesn't exist
            os.makedirs(d, exist_ok=True)
            print(f"   - Created: {d}")

    # 2. Delete State Files
    if os.path.exists("data"):
        for f in os.listdir("data"):
            if f.startswith("state_") and f.endswith(".json"):
                path = os.path.join("data", f)
                print(f"   - Deleting state file: {path}")
                os.remove(path)
            elif f == "pipeline_state.json": # Legacy support
                path = os.path.join("data", f)
                print(f"   - Deleting legacy state file: {path}")
                print(f"   - Deleting legacy state file: {path}")
                try: os.remove(path)
                except Exception as e: print(f"     ⚠️ Failed to delete {f}: {e}")

    # 3. Verification
    print("\n🔍 Verifying cleanup...")
    all_clean = True
    for d in dirs_to_clear:
        if os.path.exists(d) and len(os.listdir(d)) > 0:
            print(f"   ❌ {d} is NOT empty.")
            all_clean = False
        else:
            print(f"   ✅ {d} is empty.")
            
    if all_clean:
        print("\n✅ Pipeline has been successfully reset.")
    else:
        print("\n⚠️  Some files could not be deleted. Please check permissions.")

    print("🚀 You can now run 'python run_pipeline.py' for a fresh start.")

if __name__ == "__main__":
    # Prompt for confirmation unless -y is passed
    if "-y" not in sys.argv:
        confirm = input("⚠️ This will delete ALL processed data, OUTPUTS, and INPUT FILES. Are you sure? (y/n): ")
        if confirm.lower() != 'y':
            print("❌ Reset cancelled.")
            sys.exit(0)
    
    reset()
