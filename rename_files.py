import os
import shutil

def rename_items(base_path):
    for item in os.listdir(base_path):
        old_path = os.path.join(base_path, item)
        new_name = item.replace(" (1)", "")
        
        if new_name != item:
            new_path = os.path.join(base_path, new_name)
            try:
                if os.path.exists(new_path):
                    if os.path.isdir(old_path):
                        print(f"Directory {new_path} already exists, skipping...")
                    else:
                        print(f"File {new_path} already exists, removing old one and renaming...")
                        os.remove(new_path)
                        os.rename(old_path, new_path)
                else:
                    os.rename(old_path, new_path)
                    print(f"Renamed: {old_path} -> {new_path}")
                
                # If it's a directory, recurse
                if os.path.isdir(new_path):
                    rename_items(new_path)
            except Exception as e:
                print(f"Error renaming {old_path}: {e}")
        elif os.path.isdir(old_path):
            rename_items(old_path)

if __name__ == "__main__":
    current_dir = os.getcwd()
    print(f"Renaming files in {current_dir}...")
    rename_items(current_dir)
    print("Done.")
