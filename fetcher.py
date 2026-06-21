import os
import json
import re
import shutil
import gdown

# --- CONFIGURATION ---
GDRIVE_FOLDER_URL = "https://drive.google.com/drive/folders/1kQ0XYy0lJTnmaC6rLQIEp8azYt6vDlqZ"
TEMP_DOWNLOAD_DIR = "temp_gdrive_files"
BASE_OUTPUT_DIR = "YT_Tool_Input"

def sanitize_filename(title):
    """Removes emojis and illegal characters from the YouTube title."""
    clean_title = re.sub(r'[\\/*?:"<>|#]', "", title)
    clean_title = clean_title.encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'\s+', ' ', clean_title).strip()

def main():
    try:
        print("Downloading folder from Google Drive...")
        if os.path.exists(TEMP_DOWNLOAD_DIR):
            shutil.rmtree(TEMP_DOWNLOAD_DIR)
            
        try:
            gdown.download_folder(GDRIVE_FOLDER_URL, output=TEMP_DOWNLOAD_DIR, quiet=False, use_cookies=False)
        except Exception as e:
            print(f"Download Error: {e}")
            return

        if not os.path.exists(TEMP_DOWNLOAD_DIR) or not os.listdir(TEMP_DOWNLOAD_DIR):
            print("Download failed or folder is empty.")
            return

        json_files_paths = []
        video_files_paths = []
        for root, dirs, files in os.walk(TEMP_DOWNLOAD_DIR):
            for f in files:
                full_path = os.path.join(root, f)
                if f.endswith('.json'):
                    json_files_paths.append(full_path)
                elif f.endswith('.mp4'):
                    video_files_paths.append(full_path)

        title_tracker = {}

        for json_path in json_files_paths:
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    json_data = json.load(f)
            except:
                continue

            category = json_data.get('category', 'Uncategorized')
            raw_title = json_data.get('title', 'Unknown_Title')
            video_id = json_data.get('video_id', '')

            folder_name = f"{category}" if category.lower() in ["sad poetry"] else category
            category_dir = os.path.join(BASE_OUTPUT_DIR, folder_name)
            video_dir = os.path.join(category_dir, "YT_Video")
            json_dir = os.path.join(category_dir, "JSON")

            os.makedirs(video_dir, exist_ok=True)
            os.makedirs(json_dir, exist_ok=True)

            base_title = sanitize_filename(raw_title)
            if base_title in title_tracker:
                title_tracker[base_title] += 1
                final_title = f"{base_title}_part_{title_tracker[base_title]}"
            else:
                title_tracker[base_title] = 1
                final_title = base_title

            new_video_path = os.path.join(video_dir, f"{final_title}.mp4")
            new_json_path = os.path.join(json_dir, f"{final_title}.json")

            # Logic fix: Check if video already exists in target OR in temp
            matching_video_in_temp = next((v for v in video_files_paths if video_id in os.path.basename(v) and os.path.exists(v)), None)

            if matching_video_in_temp:
                if os.path.exists(new_video_path): os.remove(new_video_path)
                shutil.move(matching_video_in_temp, new_video_path)
                print(f"✅ Organized: {final_title}")
            elif os.path.exists(new_video_path):
                print(f"ℹ️ Video already at destination for: {final_title}")
            else:
                print(f"⚠️ Missing video for ID: {video_id}")

            if os.path.exists(new_json_path): os.remove(new_json_path)
            with open(new_json_path, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, indent=4, ensure_ascii=False)

        print("Cleaning up...")
        shutil.rmtree(TEMP_DOWNLOAD_DIR, ignore_errors=True)
        print("Batch processing complete!")

    except Exception as final_error:
        print(f"❌ A final error occurred: {final_error}")

if __name__ == '__main__':
    main()
