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
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
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
        ydl_opts = {
    # 1. ٹور پراکسی کو کوڈ کے اندر بھی سیٹ کر دیں تاکہ کوئی لیک نہ ہو
            'proxy': 'socks5://127.0.0.1:9050',
    
    # 2. یوٹیوب کو دھوکہ دینے کے لیے محفوظ اور ریل کلائنٹس کا استعمال
            'extractor_args': {
                'youtube': {
                    'player_js_version': ['actual'],
                    'player_client': ['default', 'web_safari']
                }
            },
    
    # 3. ڈیٹا سینٹر بلاکنگ سے بچنے کے لیے کوالٹی 720p پر لاک رکھیں
            'format': 'bestvideo[height<=720]+bestaudio/best',
    
    # 4. کلاؤڈ سگنیچر سالور کا استعمال
            'remote_components': 'ejs:github',
            
            'quiet': True, 'no_warnings': True, 'extract_flat': True, 'proxy': PROXY_URL if PROXY_URL and "http" in PROXY_URL else None}
      
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

# --- Multi-Site Fallback Download Function ---
def download_video_with_fallback(video_url, output_path, category_name):
    """
    Sequential fallback mechanism: yt-dlp → Cobalt → SaveFrom → Coar.is
    Returns True if successful, False otherwise.
    """
    
    # Step 1: Try native yt-dlp
    print(f"    [Step 1] Attempting yt-dlp download...")
    try:
        ydl_opts = {
            'outtmpl': output_path,
            'format': 'mp4',
            'quiet': True,
            'proxy': PROXY_URL if PROXY_URL and "http" in PROXY_URL else None
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            tmp = ydl.prepare_filename(info)
        print(f"    ✅ yt-dlp succeeded")
        return tmp
    except Exception as e:
        print(f"    ❌ yt-dlp failed: {str(e)[:80]}")
    
    # Step 2: Fallback to Cobalt Public API
    print(f"    [Step 2] Attempting Cobalt API fallback...")
    try:
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        payload = {
            "url": video_url,
            "vQuality": "720"
        }
        response = requests.post(
            'https://api.cobalt.tools/api/json',
            json=payload,
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        
        if data.get('status') == 'success' and data.get('url'):
            download_url = data['url']
            return _stream_download_video(download_url, output_path)
    except Exception as e:
        print(f"    ❌ Cobalt failed: {str(e)[:80]}")
    
    # Step 3: Fallback to SaveFrom.net Worker API
    print(f"    [Step 3] Attempting SaveFrom.net fallback...")
    try:
        payload = {
            'url': video_url,
            'current_url': video_url
        }
        response = requests.post(
            'https://worker.sf-api.com/savefrom.php',
            data=payload,
            timeout=30,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        )
        response.raise_for_status()
        
        # Parse direct MP4 stream URL using regex
        match = re.search(r'https?://[^\s"<>]+\.mp4[^\s"<>]*', response.text)
        if match:
            download_url = match.group(0)
            return _stream_download_video(download_url, output_path)
    except Exception as e:
        print(f"    ❌ SaveFrom failed: {str(e)[:80]}")
    
    # Step 4: Fallback to Coar.is API
    print(f"    [Step 4] Attempting Coar.is API fallback...")
    try:
        response = requests.get(
            f'https://coar.is/api/download?url={requests.utils.quote(video_url)}',
            timeout=30,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        )
        response.raise_for_status()
        data = response.json()
        
        if data.get('success') and data.get('url'):
            download_url = data['url']
            return _stream_download_video(download_url, output_path)
    except Exception as e:
        print(f"    ❌ Coar.is failed: {str(e)[:80]}")
    
    # All fallbacks exhausted
    print(f"    ❌ All fallback methods failed")
    return None

def _stream_download_video(download_url, output_path):
    """
    Stream-download video in chunks to prevent memory lag.
    Returns the final file path on success, None on failure.
    """
    try:
        response = requests.get(
            download_url,
            timeout=60,
            stream=True,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        )
        response.raise_for_status()
        
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Stream download in 8KB chunks
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        # Verify file exists and has content
        if os.path.getsize(output_path) > 0:
            print(f"    ✅ Stream download succeeded ({os.path.getsize(output_path)} bytes)")
            return output_path
        else:
            os.remove(output_path)
            return None
    except Exception as e:
        print(f"    ❌ Stream download failed: {str(e)[:80]}")
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except:
                pass
        return None

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

                for entry in feed.entries:
                    pub = parser.parse(entry.published).astimezone(timezone.utc)
                    if pub > last_run_dt:
                        print(f"  ⬆️ New video: {entry.title}")
                        
                        # Generate output path matching original template
                        video_id = entry.link.split('v=')[-1].split('&')[0] if 'v=' in entry.link else entry.link.split('/')[-1]
                        output_path = os.path.join(os.getcwd(), f'vid_{video_id}_{cat}.mp4')
                        
                        # Use multi-fallback downloader
                        tmp = download_video_with_fallback(entry.link, output_path, cat)
                        
                        if tmp and os.path.exists(tmp):
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
                        else:
                            print(f"  ❌ Failed to download video after all fallbacks")

            supabase.table(table_name).update({last_run_col: datetime.now(timezone.utc).isoformat()}).eq(id_col, row_id).execute()
    except Exception as e: print(f"Error: {e}")

run_batch_process()
print("✅ Multi-channel process finished.")
