import os
import sys
import requests
from datetime import datetime, timedelta
import google.generativeai as genai
from supabase import create_client, Client

# Handle MoviePy imports based on version
try:
    from moviepy import VideoFileClip
except ImportError:
    from moviepy.editor import VideoFileClip

# ==========================================
# 1. Secure Configuration (Env Variables)
# ==========================================
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

TABLE_NAME = "viral_reports"
# Adjusted to match standard GitHub Actions structure (removed 'content/')
SOURCE_FOLDER_PATH = "YT_output_CC" 
THUMBNAIL_FOLDER_PATH = os.path.join(SOURCE_FOLDER_PATH, "thum")
POSTING_SCHEDULE = ["10:00 AM", "02:00 PM", "06:00 PM", "10:00 PM"]

# ==========================================
# 2. System Initialization
# ==========================================
if not all([SUPABASE_URL, SUPABASE_KEY, DISCORD_WEBHOOK_URL, GEMINI_API_KEY]):
    print("❌ ERROR: Missing one or more environment variables. Check GitHub Secrets.")
    sys.exit(1)

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash')
except Exception as e:
    print(f"❌ Initialization Failed: {e}")
    sys.exit(1)

os.makedirs(THUMBNAIL_FOLDER_PATH, exist_ok=True)

# ==========================================
# 3. Core Functions
# ==========================================
def upload_to_discord(file_path):
    """Uploads video to Discord and retrieves the direct CDN link."""
    try:
        with open(file_path, 'rb') as f:
            webhook_url_with_wait = f"{DISCORD_WEBHOOK_URL}?wait=true"
            response = requests.post(webhook_url_with_wait, files={'file': f})
            
            if response.status_code in [200, 201, 204]:
                data = response.json()
                if 'attachments' in data and len(data['attachments']) > 0:
                    return data['attachments'][0]['url']
                return "SUCCESS: Uploaded (Link not found in response)"
            return f"Discord Error: {response.status_code}"
    except Exception as e:
        return f"Discord Upload Failed: {e}"

def get_last_post_time_from_db():
    """Fetches the latest scheduled time from Supabase."""
    try:
        res = supabase.table(TABLE_NAME).select("scheduled_time").order("scheduled_time", desc=True).limit(1).execute()
        if res.data:
            return datetime.strptime(res.data[0]['scheduled_time'], "%Y-%m-%d %I:%M %p")
    except Exception as e:
        print(f"⚠️ DB Time Fetch Error: {e}")
    return None

def get_next_schedule_slot(last_dt):
    """Calculates the next available slot based on the fixed array variable."""
    schedule_times = [datetime.strptime(t, "%I:%M %p").time() for t in POSTING_SCHEDULE]
    schedule_times.sort()
    
    if last_dt is None:
        last_dt = datetime.now()
        
    for s_time in schedule_times:
        potential_dt = datetime.combine(last_dt.date(), s_time)
        if potential_dt > last_dt: 
            return potential_dt
            
    # If all slots for the day are passed, roll over to the first slot of the next day
    return datetime.combine(last_dt.date() + timedelta(days=1), schedule_times[0])

# ==========================================
# 4. Main Processing Engine
# ==========================================
def process_videos():
    if not os.path.exists(SOURCE_FOLDER_PATH):
        print(f"📁 Creating source folder '{SOURCE_FOLDER_PATH}'...")
        os.makedirs(SOURCE_FOLDER_PATH, exist_ok=True)

    for root, dirs, files in os.walk(SOURCE_FOLDER_PATH):
        if 'thum' in dirs: 
            dirs.remove('thum')
            
        videos = [f for f in files if f.lower().endswith(('.mp4', '.mov', '.avi'))]
        if not videos: 
            continue

        video_category = os.path.basename(root) or "General"
        print(f"\n📊 Processing Folder: {video_category}")
        last_dt = get_last_post_time_from_db()

        for video in videos:
            v_path = os.path.join(root, video)
            next_dt = get_next_schedule_slot(last_dt)
            formatted_time = next_dt.strftime("%Y-%m-%d %I:%M %p")
            last_dt = next_dt

            print(f"\n🎬 Video: {video} | ⏰ Scheduled: {formatted_time}")

            # 1. AI Metadata Generation
            try:
                prompt = (
                    f"Video: {video}. Act as a viral social media expert. "
                    "Generate 11 elements separated by ' | ': Title, Desc, Tags, TikTok, IG, FB, Popular, Hashtags, Event, Keywords, Snap. "
                    "\nRequirements: India/UK trends, Emojis. Strictly use ' | '."
                )
                ai_response = model.generate_content(prompt).text.strip()
                ai_data = ai_response.split(' | ')
            except Exception as e:
                print(f"  ⚠️ AI Error: {e}")
                ai_data = ["Error"] * 11

            while len(ai_data) < 11: 
                ai_data.append("N/A")

            # 2. Discord Upload
            print(f"  🚀 Uploading to Discord...")
            direct_video_link = upload_to_discord(v_path)
            print(f"  🔗 Direct Link: {direct_video_link}")

            # 3. Thumbnail Extraction
            thumb_local_path = os.path.join(THUMBNAIL_FOLDER_PATH, f"{video}_thumb.png")
            try:
                if not os.path.exists(thumb_local_path):
                    with VideoFileClip(v_path) as clip: 
                        clip.save_frame(thumb_local_path, t=1.0)
            except Exception as e:
                print(f"  ⚠️ Thumbnail Error: {e}")

            # 4. Supabase Database Insert
            payload = {
                "video_name": video,
                "status": "pending",
                "scheduled_time": formatted_time,
                "video_local_path": v_path,
                "thumb_local_path": thumb_local_path,
                "yt_title": ai_data[0],
                "yt_description": ai_data[1],
                "yt_tags": ai_data[2],
                "tiktok_caption": ai_data[3],
                "instagram_caption": ai_data[4],
                "fb_caption": ai_data[5],
                "popular_captions": ai_data[6],
                "hashtags": ai_data[7],
                "trending_event": ai_data[8],
                "keywords": ai_data[9],
                "snapchat": ai_data[10],
                "discord_link": direct_video_link,
                "video_type": video_category
            }

            try:
                supabase.table(TABLE_NAME).insert(payload).execute()
                print(f"  ✅ Row inserted into Supabase table '{TABLE_NAME}'!")
            except Exception as e:
                print(f"  ❌ Insert Failed: {e}")

    print("\n✨ Finished. Process completed.")

if __name__ == "__main__":
    process_videos()
