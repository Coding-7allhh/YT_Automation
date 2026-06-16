#!/usr/bin/env python
# coding: utf-8

import os, re, requests, yt_dlp, feedparser, time, shutil
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from supabase import create_client, Client
from datetime import datetime, timezone
from dateutil import parser
import subprocess
import warnings

# --- کنفیگریشن (Config) ---
# انوائرنمنٹ ویری ایبلز کو محفوظ طریقے سے GitHub Secrets سے لیا گیا ہے
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://khbkyqgnpvyksqxmcvzl.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "sb_publishable_l5DfqNwsJ-yLliPtNBDv6g_jfUK1CoH")
table_name = "Channel_url"

# اہم: YT بلاکنگ سے بچنے کے لیے ایک درست پراکسی (مثلاً http://user:pass@host:port) استعمال کریں
PROXY_URL = os.environ.get("YT_PROXY")

# --- Setup ---
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
base_dir = os.path.abspath("content/YT_Tool_Input")
blogger_dir = os.path.abspath("content/output/Blogger")
os.makedirs(base_dir, exist_ok=True)
os.makedirs(blogger_dir, exist_ok=True)

try:
    if not SUPABASE_KEY or "REPLACE" in SUPABASE_KEY:
        print("❌ Error: SUPABASE_KEY not found.")
        supabase = None
    else:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("✅ Supabase connected")
except Exception as e:
    print(f"❌ Supabase connection failed: {e}")
    supabase = None

# --- Helper Functions ---
def get_video_metadata(video_path):
    try:
        cmd = ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height,duration', '-of', 'default=noprint_wrappers=1:nokey=1', video_path]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, text=True).stdout.splitlines()
        if not result or len(result) < 3: return None, None
        width, height, duration = int(result[0]), int(result[1]), float(result[2])
        return duration, ("9:16" if width < height else "16:9")
    except: return None, None

def get_youtube_rss_robust(url):
    try:
        if "feeds/videos.xml" in url: return url
        ydl_opts = {'quiet': True, 'no_warnings': True, 'extract_flat': True, 'proxy': PROXY_URL if PROXY_URL and "http" in PROXY_URL else None}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            cid = info.get('channel_id') or info.get('id')
            if cid and str(cid).startswith('UC'):
                return f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
        return None
    except: return None

def make_shorts_with_blur(video_path, category_name):
    try:
        duration, _ = get_video_metadata(video_path)
        if not duration: return False
        save_dir = os.path.join(base_dir, category_name)
        os.makedirs(save_dir, exist_ok=True)
        name = os.path.splitext(os.path.basename(video_path))[0]
        blur = "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20:10[bg];[0:v]scale=1080:-1[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2"
        for i, start in enumerate(range(0, int(duration), 15), 1):
            if start + 10 > duration: break
            out = os.path.join(save_dir, f"{name}_Part_{i}.mp4")
            cmd = ['ffmpeg', '-y', '-ss', str(start), '-i', video_path, '-t', '15', '-filter_complex', blur, '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '23', '-c:a', 'aac', '-b:a', '128k', out]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except: return False

def run_batch_process():
    if supabase is None: return
    try:
        response = supabase.table(table_name).select("*").execute()
        rows = response.data
        if not rows: return

        all_keys = list(rows[0].keys())
        id_col = "id" if "id" in all_keys else all_keys[0]
        last_run_col = "last_run" if "last_run" in all_keys else all_keys[1]
        categories = [k for k in all_keys if k not in [id_col, last_run_col]]

        for row in rows:
            row_id = row.get(id_col)
            last_run_str = row.get(last_run_col)
            last_run_dt = parser.isoparse(last_run_str).astimezone(timezone.utc) if last_run_str else datetime(2000, 1, 1, tzinfo=timezone.utc)

            for cat in categories:
                url = str(row.get(cat, "")).strip()
                if "http" not in url: continue

                print(f"⏳ Fetching {cat} from {url}...")
                rss = get_youtube_rss_robust(url)
                if not rss: continue

                feed = feedparser.parse(rss)
                ydl_opts = {'outtmpl': os.path.join(os.getcwd(), f'vid_%(id)s_{cat}.mp4'), 'format': 'mp4', 'quiet': True, 'proxy': PROXY_URL if PROXY_URL and "http" in PROXY_URL else None}

                for entry in feed.entries:
                    pub = parser.parse(entry.published).astimezone(timezone.utc)
                    if pub > last_run_dt:
                        print(f"  ⬆️ New video: {entry.title}")
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            info = ydl.extract_info(entry.link, download=True)
                            tmp = ydl.prepare_filename(info)

                        dur, ratio = get_video_metadata(tmp)
                        if ratio == "9:16":
                            dest = os.path.join(base_dir, cat)
                            os.makedirs(dest, exist_ok=True)
                            shutil.move(tmp, os.path.join(dest, os.path.basename(tmp)))
                        else:
                            make_shorts_with_blur(tmp, cat)
                            b_dest = os.path.join(blogger_dir, cat)
                            os.makedirs(b_dest, exist_ok=True)
                            shutil.move(tmp, os.path.join(b_dest, os.path.basename(tmp)))

            supabase.table(table_name).update({last_run_col: datetime.now(timezone.utc).isoformat()}).eq(id_col, row_id).execute()
    except Exception as e: print(f"Error: {e}")

run_batch_process()
print("✅ Multi-channel process finished.")
