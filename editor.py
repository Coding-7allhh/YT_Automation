#!/usr/bin/env python
# coding: utf-8

import subprocess, os, glob, time, json, re
from tqdm import tqdm
import google.generativeai as genai
from PIL import Image
from concurrent.futures import ThreadPoolExecutor

# ================= 1. SETUP & API KEY =================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("❌ Error: GEMINI_API_KEY not found in environment secrets.")
    exit(1)

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

# ================= 2. PATHS & SETTINGS =================
# Dynamically aligns with GitHub's runner workspace
BASE_PATH = os.getcwd()
INPUT_DIR  = os.path.join(BASE_PATH, "YT_Tool_Input")
OUTPUT_DIR = os.path.join(BASE_PATH, "YT_Tool_output")
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
all_video_paths = glob.glob(os.path.join(INPUT_DIR, "**/*.mp4"), recursive=True)

# --- ADJUST THESE FOR VIDEO SIZE ---
OUT_W, OUT_H = 1080, 1920
CENTER_W, CENTER_H = 980, 1455
ZOOM_FACTOR = 0.8
ZOOM_OUT_SPEED = 0.3

def clean_for_ffmpeg(text):
    return re.sub(r'[^a-zA-Z0-9 ]', '', text)

def get_ai_text(video_path, vid_id):
    frame_path = f"temp_frame_{vid_id}.jpg"
    subprocess.run(["ffmpeg", "-y", "-i", video_path, "-ss", "00:00:02", "-vframes", "1", frame_path], capture_output=True)
    for attempt in range(2):
        try:
            time.sleep(5)
            img = Image.open(frame_path)
            prompt = "Analyze this image for a viral short. Give me 1 catchy top line (max 3 words) and 1 emotional bottom line (max 5 words). Return JSON: {'top': '...', 'sub': '...'}"
            response = model.generate_content([prompt, img])
            data = json.loads(response.text.replace("```json", "").replace("```", "").strip())
            return clean_for_ffmpeg(data['top']).upper(), clean_for_ffmpeg(data['sub']).upper()
        except:
            continue
    return "AMAZING MOMENT", "WATCH UNTIL END"

def process_single_video(INPUT):
    rel_path = os.path.relpath(INPUT, INPUT_DIR)
    FINAL_OUT = os.path.join(OUTPUT_DIR, rel_path).replace(" ", "_")
    os.makedirs(os.path.dirname(FINAL_OUT), exist_ok=True)

    vid_name = os.path.basename(INPUT)
    vid_id = abs(hash(vid_name))

    print(f"\n✨ Pro-Processing: {vid_name}")
    AI_TOP, AI_SUB = get_ai_text(INPUT, vid_id)

    try:
        dur_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", INPUT]
        dur = float(subprocess.check_output(dur_cmd).decode().strip())
        new_dur = dur + 4

        audio_check = subprocess.run(["ffprobe", "-show_streams", "-select_streams", "a", "-loglevel", "error", INPUT], capture_output=True, text=True)
        has_audio = len(audio_check.stdout) > 0
        audio_input = "[0:a]" if has_audio else "anullsrc=channel_layout=stereo:sample_rate=44100[a_dummy];[a_dummy]"

        z_expr = f"{ZOOM_FACTOR}+{ZOOM_OUT_SPEED}*sin(2*PI*2*on/({new_dur}*25))"

        filter_complex = (
            f"[0:v]split=2[v_bg][v_fg];"
            f"[v_bg]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase,crop={OUT_W}:{OUT_H},boxblur=30[bg_layer];"
            f"[v_fg]scale={CENTER_W}:{CENTER_H},zoompan=z='{z_expr}':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={CENTER_W}x{CENTER_H},format=yuva420p[fg_zoomed];"
            f"[bg_layer][fg_zoomed]overlay=x=(W-w)/2:y=(H-h)/2[base];"
            f"[base]drawtext=fontfile='{FONT}':text='{AI_TOP}':fontsize=85:fontcolor=yellow:borderw=5:bordercolor=black:shadowx=3:shadowy=3:x=(w-text_w)/2:y=30,"
            f"drawtext=fontfile='{FONT}':text='{AI_SUB}':fontsize=50:fontcolor=white:borderw=4:bordercolor=0xFF00FF:shadowx=2:shadowy=2:x=(w-text_w)/2:y=146,"
            f"drawtext=fontfile='{FONT}':text='LIKE • SHARE • COMMENT':fontsize=40:fontcolor=white:borderw=3:bordercolor=0x00FFFF:shadowx=2:shadowy=2:x=(w-text_w)/2:y=h-200,"
            f"drawtext=fontfile='{FONT}':text='FOLLOW FOR MORE':fontsize=45:fontcolor=white:borderw=3:bordercolor=red:shadowx=2:shadowy=2:x=(w-text_w)/2:y=h-140,"
            f"drawtext=fontfile='{FONT}':text='RAJPUT ADS AGENCY':fontsize=65:fontcolor=yellow:borderw=5:bordercolor=0xFFD700:shadowx=3:shadowy=3:x=(w-text_w)/2:y=h-75,format=yuv420p[v_final];"
            f"{audio_input}atrim=0:{dur},asetpts=PTS-STARTPTS,aresample=44100,pan=stereo|c0=c0|c1=c1[a_orig]"
        )

        subprocess.run([
            "ffmpeg", "-y", "-i", INPUT,
            "-filter_complex", filter_complex,
            "-map", "[v_final]", "-map", "[a_orig]",
            "-t", str(new_dur), "-r", "25", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", FINAL_OUT
        ], check=True)
        print(f"✅ Saved Successfully: {FINAL_OUT}")
    except Exception as e:
        print(f"❌ Save Error: {e}")

if not all_video_paths:
    print(f"⚠️ NO VIDEOS FOUND! Make sure .mp4 files are in: {INPUT_DIR}")
else:
    print(f"᎐᎐᎐ SAME-TO-SAME Editor Active | ᎐ Total: {len(all_video_paths)}")
    with ThreadPoolExecutor(max_workers=1) as executor:
        list(tqdm(executor.map(process_single_video, all_video_paths), total=len(all_video_paths)))
    print("\n᎐᎐᎐ COMPLETED!")
