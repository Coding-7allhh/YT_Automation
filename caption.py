#!/usr/bin/env python
# coding: utf-8

# In[ ]:


# ==========================================
# 1. System Setup (English CC + Magic Logo)
# ==========================================
import os
print("ጓ FINAL REPAIR: English Captions & Magic Colorful Border | Full HD & 2K Support...")

# Clean installation of necessary libraries (Removed Arabic tools)
#os.system("pip uninstall -y moviepy")
#os.system("pip install moviepy==1.0.3 assemblyai google-generativeai pydub numpy gdown")
#os.system("apt-get update -qq && apt-get install -y imagemagick fonts-liberation -qq")

# ImageMagick Unlock
#os.system("sed -i 's/domain=\"path\" rights=\"none\" pattern=\"@\\*\"/domain=\"path\" rights=\"read|write\" pattern=\"@\\*\"/g' /etc/ImageMagick-6/policy.xml")

import glob
import time
import random
import numpy as np
import assemblyai as aai
import google.generativeai as genai
import gdown
from PIL import Image, ImageDraw, ImageFilter
from pydub import AudioSegment
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip, ImageClip, ColorClip, concatenate_videoclips
from moviepy.video.tools.subtitles import SubtitlesClip
from moviepy.config import change_settings

# Pillow compatibility for different versions: ensure ANTIALIAS / Resampling exist
# Some Pillow versions removed Image.ANTIALIAS in favor of Image.Resampling.LANCZOS
try:
    _ = Image.Resampling
except Exception:
    class _Resampling:
        LANCZOS = getattr(Image, 'LANCZOS', getattr(Image, 'ANTIALIAS', 1))
    Image.Resampling = _Resampling
if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.Resampling.LANCZOS

#change_settings({"IMAGEMAGICK_BINARY": "/usr/bin/convert"})

# ==========================================
# 2. Settings
# ==========================================
ASSEMBLYAI_KEY = os.environ.get("ASSEMBLYAI_KEY", "YOUR_ASSEMBLYAI_KEY_HERE")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "YOUR_GEMINI_KEY_HERE")

aai.settings.api_key = ASSEMBLYAI_KEY
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel('gemini-2.0-flash')

BASE_DIR = "YT_Tool_output"
OUTPUT_BASE_DIR = "YT_output_CC"
LOGOS_BASE_DIR = "BG music/logo_img"
SRT_CACHE_DIR = "SRT_Cache"

# Google Drive folder ID containing all logos
DRIVE_LOGOS_FOLDER_ID = "1bt00qzL87Z5i4CLtuFUixzQASIyDybNj"
DRIVE_OUTRO_URL = "https://drive.google.com/uc?id=1GgAxpDiYLOkv0E_BXjCpbvCr7oH-f_Vt"

OUTRO_PATH = "downloaded_outro.mp4"

# ==========================================
# VIDEO QUALITY SETTINGS (ENHANCED)
# ==========================================
VIDEO_QUALITY = "2K"  # Options: "1080p", "2K", "4K"
FPS_OUTPUT = 60  # 60 FPS for smooth video
BITRATE = "8000k"  # Bitrate for 2K quality

# Resolution presets
RESOLUTION_PRESETS = {
    "1080p": (1920, 1080),
    "2K": (2560, 1440),
    "4K": (3840, 2160)
}

TARGET_RESOLUTION = RESOLUTION_PRESETS[VIDEO_QUALITY]

os.makedirs(BASE_DIR, exist_ok=True)
os.makedirs(OUTPUT_BASE_DIR, exist_ok=True)
os.makedirs(LOGOS_BASE_DIR, exist_ok=True)
os.makedirs(SRT_CACHE_DIR, exist_ok=True)

if not os.path.exists(OUTRO_PATH):
    gdown.download(DRIVE_OUTRO_URL, OUTRO_PATH, quiet=True)

# Debug: show whether downloads succeeded
print("DEBUG: downloaded_outro exists:", os.path.exists(OUTRO_PATH))
print(f"VIDEO QUALITY: {VIDEO_QUALITY} {TARGET_RESOLUTION[0]}x{TARGET_RESOLUTION[1]} @ {FPS_OUTPUT} FPS")

# ==========================================
# 3. Functions
# ==========================================

def get_logo_from_drive(folder_id, logo_name):
    """
    Downloads a logo from Google Drive folder by name.
    Returns the local path if found, None otherwise.
    """
    try:
        # Use gdown to list and download files from folder
        logo_path = os.path.join(LOGOS_BASE_DIR, f"{logo_name}.png")
        
        # Check if logo already exists locally
        if os.path.exists(logo_path):
            print(f"♻ᄂ Using cached logo: {logo_name}")
            return logo_path
        
        # Try downloading from Drive folder
        # Format: https://drive.google.com/drive/folders/FOLDER_ID
        drive_folder_url = f"https://drive.google.com/drive/folders/{folder_id}"
        
        print(f"ጡ Attempting to download logo: {logo_name}")
        
        # Use gdown to download from folder - it will attempt to find the file
        try:
            gdown.download_folder(drive_folder_url, output=LOGOS_BASE_DIR, quiet=True)
            
            # Look for the logo file after download
            possible_paths = [
                logo_path,
                os.path.join(LOGOS_BASE_DIR, f"{logo_name}"),
                os.path.join(LOGOS_BASE_DIR, f"{logo_name}.jpg"),
                os.path.join(LOGOS_BASE_DIR, f"{logo_name}.jpeg")
            ]
            
            for path in possible_paths:
                if os.path.exists(path):
                    print(f"✅ Logo found: {path}")
                    return path
        except Exception as e:
            print(f"⚠ᄂ Folder download failed: {e}")
        
        print(f"❌ Logo not found: {logo_name}")
        return None
    except Exception as e:
        print(f"⚠ᄂ Error downloading logo: {e}")
        return None

def create_fallback_srt(path, duration):
    """Creates a dummy English SRT if the API fails."""
    phrases = ["Beautiful moments", "Enjoy the vibe", "Peace and calm", "Amazing journey", "Keep moving forward", "Magic in the air"]
    content = ""
    step = duration / 6
    for i in range(6):
        start = time.strftime('%H:%M:%S,000', time.gmtime(i * step))
        end = time.strftime('%H:%M:%S,000', time.gmtime((i + 1) * step))
        content += f"{i+1}\n{start} --> {end}\n{random.choice(phrases)}\n\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path

def generate_english_srt(video_name, duration, max_retries=2):
    """Generates English SRT with 2-try limit and fallback logic."""
    safe_name = "".join([c if c.isalnum() else "_" for c in video_name])
    cache_path = os.path.join(SRT_CACHE_DIR, f"{safe_name}.srt")

    if os.path.exists(cache_path) and os.path.getsize(cache_path) > 20:
        print(f"♻ᄂ Reusing cached SRT for: {video_name}")
        return cache_path

    print(f"ጡ Attempting Gemini English captions for: {video_name}")
    prompt = f"Generate a professional English SRT file for a {duration} second video. Return ONLY raw SRT text."

    for attempt in range(max_retries):
        try:
            response = gemini_model.generate_content(prompt)
            srt_text = response.text.strip()
            if "```" in srt_text:
                srt_text = srt_text.split("```")[1].replace("srt", "").strip()
            with open(cache_path, "w", encoding="utf-8") as f:
                f.write(srt_text)
            return cache_path
        except Exception as e:
            wait_time = 15
            print(f"⚠ᄂ API Busy (Try {attempt+1}/{max_retries}). Waiting {wait_time}s...")
            time.sleep(wait_time)

    print(f"ጡ Creating placeholder SRT for: {video_name}")
    return create_fallback_srt(cache_path, duration)

def prepare_full_frame_outro(main_clip, outro_path):
    if not os.path.exists(outro_path):
        print(f"prepare_full_frame_outro: outro file not found: {outro_path}")
        return None
    try:
        outro = VideoFileClip(outro_path)
        # Resize to target resolution
        outro_fitted = outro.resize(width=TARGET_RESOLUTION[0], height=TARGET_RESOLUTION[1])
        bg = ColorClip(size=TARGET_RESOLUTION, color=(0,0,0)).set_duration(outro.duration)
        return CompositeVideoClip([bg, outro_fitted.set_position('center')]).set_audio(outro.audio)
    except Exception as e:
        print(f"prepare_full_frame_outro error: {e}")
        return None

def create_deep_magic_colors(angle, intensity=1.0):
    """
    Creates DEEP, vibrant magic colors using enhanced color schemes.
    Returns RGB tuple with higher saturation and deeper, richer tones.
    """
    # Enhanced magic color palette with deeper saturation
    r = int((np.sin(angle * 2.5 + 0) + 1) * 127.5 * intensity)
    g = int((np.sin(angle * 2.5 + 2*np.pi/3) + 1) * 127.5 * intensity)
    b = int((np.sin(angle * 2.5 + 4*np.pi/3) + 1) * 127.5 * intensity)
    
    # Boost saturation for DEEP, RICH colors
    max_val = max(r, g, b)
    min_val = min(r, g, b)
    
    if max_val > 0:
        # Increase saturation
        r = min(255, int(r * 1.4))
        g = min(255, int(g * 1.4))
        b = min(255, int(b * 1.4))
        
        # Add brightness boost for deeper tones
        r = min(255, int(r * 1.15))
        g = min(255, int(g * 1.15))
        b = min(255, int(b * 1.15))
    
    return (r, g, b)

def make_magic_growing_logo(video_width, video_height, duration, logo_path):
    """
    Creates a circular logo with a DEEP multi-color swirl border and smooth pulsing effect.
    Enhanced for 2K/4K resolution with DEEPER, more vibrant magic colors.
    """
    if not os.path.exists(logo_path):
        print(f"make_magic_growing_logo: logo file not found: {logo_path}")
        return None
    try:
        # Scale logo size for higher resolution (larger for 2K/4K)
        size = int(video_width * 0.20)
        border_width = int(size * 0.10)  # Thicker border for 2K
        b_size = size + 2 * border_width
        temp_logo_path = "temp_magic_logo.png"

        logo_img = Image.open(logo_path).convert("RGBA")
        w, h = logo_img.size
        min_dim = min(w, h)
        logo_img = logo_img.crop(((w-min_dim)//2, (h-min_dim)//2, (w+min_dim)//2, (h+min_dim)//2)).resize((size, size), Image.Resampling.LANCZOS)

        # Create circular mask with high-quality anti-aliasing
        mask = Image.new('L', (size, size), 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0, size-1, size-1), fill=255)

        circular_logo = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        circular_logo.paste(logo_img, (0, 0), mask=mask)

        # ENHANCED magic border with DEEPER, more vibrant colors
        border_img = Image.new('RGBA', (b_size, b_size), (0, 0, 0, 0))
        for x in range(b_size):
            for y in range(b_size):
                dx, dy = x - b_size/2, y - b_size/2
                dist = (dx**2 + dy**2)**0.5
                if (size/2) <= dist <= (b_size/2):
                    angle = np.arctan2(dy, dx)
                    # Create DEEP magic colors
                    r, g, b = create_deep_magic_colors(angle, intensity=1.2)
                    border_img.putpixel((x, y), (r, g, b, 255))

        final_img = Image.new('RGBA', (b_size, b_size), (0, 0, 0, 0))
        # Apply Gaussian blur for smooth, glowing transition
        final_img.paste(border_img.filter(ImageFilter.GaussianBlur(3)), (0, 0))
        final_img.paste(circular_logo, (border_width, border_width), circular_logo)
        final_img.save(temp_logo_path)

        # Enhanced pulsing effect with smoother, more dramatic animation
        logo_clip = ImageClip(temp_logo_path, transparent=True).resize(lambda t: 1.0 + 0.10 * np.sin(2.0 * t))

        def pos_func(t):
            sx, sy = (40, 40)
            tx, ty = (video_width - b_size - 40, video_height - b_size - 40)
            if t < 2: p = t / 2
            elif t < 4: p = 1 - ((t - 2) / 2)
            elif t < 6: p = (t - 4) / 2
            else: return (tx, ty)
            return (sx + (tx - sx) * p, sy + (ty - sy) * p)

        return logo_clip.set_duration(duration).set_position(pos_func).crossfadein(0.5)
    except Exception as e:
        print(f"make_magic_growing_logo error: {e}")
        return None

def create_magic_caption_bg(width, height, border_w=8):
    """
    Generates a DEEP magic colorful border background for captions.
    Enhanced with DEEPER, more vibrant colors for 2K resolution.
    """
    full_w, full_h = width + 2*border_w, height + 2*border_w
    bg_img = Image.new('RGBA', (full_w, full_h), (0, 0, 0, 0))
    for x in range(full_w):
        for y in range(full_h):
            is_border = x < border_w or x > width + border_w or y < border_w or y > height + border_w
            if is_border:
                angle = np.arctan2(y - full_h/2, x - full_w/2)
                # Use DEEP magic colors for border
                r, g, b = create_deep_magic_colors(angle, intensity=1.2)
                bg_img.putpixel((x, y), (r, g, b, 255))
            else:
                # Darker, more transparent center for better text visibility
                bg_img.putpixel((x, y), (0, 0, 0, 220))

    path = "caption_magic_bg.png"
    bg_img.save(path)
    return path

def upscale_video_resolution(video_clip, target_width, target_height):
    """
    Upscales video to target resolution while maintaining aspect ratio.
    Uses high-quality resizing for 2K/4K output.
    """
    original_aspect = video_clip.w / video_clip.h
    target_aspect = target_width / target_height
    
    if original_aspect > target_aspect:
        # Fit to width
        new_width = target_width
        new_height = int(target_width / original_aspect)
    else:
        # Fit to height
        new_height = target_height
        new_width = int(target_height * original_aspect)
    
    # Upscale and center with padding
    resized = video_clip.resize(width=new_width, height=new_height)
    padded = CompositeVideoClip(
        [ColorClip(size=(target_width, target_height), color=(0, 0, 0)), 
         resized.set_position('center')],
        size=(target_width, target_height)
    )
    return padded

def run_fast_engine():
    videos = glob.glob(os.path.join(BASE_DIR, "**/*.mp4"), recursive=True)
    for video_path in videos:
        video_filename = os.path.basename(video_path)
        rel_path = os.path.relpath(video_path, BASE_DIR)
        out_dir = os.path.join(OUTPUT_BASE_DIR, os.path.dirname(rel_path))
        os.makedirs(out_dir, exist_ok=True)

        # Get parent folder name to use as logo name
        parent_folder = os.path.basename(os.path.dirname(video_path))
        
        print(f"\nፁ Processing: {rel_path}")
        print(f"ጡ Parent folder (logo name): {parent_folder}")
        print(f"ጡ Upscaling to: {VIDEO_QUALITY} {TARGET_RESOLUTION[0]}x{TARGET_RESOLUTION[1]} @ {FPS_OUTPUT} FPS")
        
        try:
            main_clip = VideoFileClip(video_path)
            
            # Upscale original video to target resolution
            main_clip = upscale_video_resolution(main_clip, TARGET_RESOLUTION[0], TARGET_RESOLUTION[1])
            
            srt_file = generate_english_srt(video_filename, main_clip.duration)
            current_video = main_clip

            if srt_file and os.path.exists(srt_file):
                try:
                    def generator(t):
                        # Generate Text with larger font for 2K
                        font_size = int(65 * (TARGET_RESOLUTION[0] / 1920))
                        txt = TextClip(
                            t,
                            font='Liberation-Sans-Bold',
                            fontsize=font_size,
                            color='yellow',
                            method='caption',
                            align='center',
                            size=(int(TARGET_RESOLUTION[0] * 0.88), None)
                        )
                        # Create DEEP Magic Border Background
                        bg_path = create_magic_caption_bg(txt.w, txt.h, border_w=10)
                        bg_clip = ImageClip(bg_path).set_duration(txt.duration)
                        # Layer Text over DEEP Magic Background
                        return CompositeVideoClip([bg_clip, txt.set_position('center')], size=bg_clip.size)

                    subs = SubtitlesClip(srt_file, generator)
                    current_video = CompositeVideoClip([main_clip, subs.set_position(('center', int(TARGET_RESOLUTION[1] * 0.82)))], size=TARGET_RESOLUTION)
                except Exception as e:
                    print(f"⚠ᄂ Overlay failed: {e}")

            # Download and use logo based on parent folder name
            logo_path = get_logo_from_drive(DRIVE_LOGOS_FOLDER_ID, parent_folder)
            
            if logo_path:
                logo = make_magic_growing_logo(TARGET_RESOLUTION[0], TARGET_RESOLUTION[1], main_clip.duration, logo_path)
                print("DEBUG: logo object:", logo, "duration:", getattr(logo, 'duration', None), "size:", getattr(logo, 'size', None))
                if logo:
                    # Ensure overlay size matches main clip
                    current_video = CompositeVideoClip([current_video, logo], size=TARGET_RESOLUTION)
            else:
                print(f"⚠ᄂ Logo not found for folder: {parent_folder}")

            final_render = current_video
            outro = prepare_full_frame_outro(main_clip, OUTRO_PATH)
            print("DEBUG: outro object:", outro, "duration:", getattr(outro, 'duration', None), "size:", getattr(outro, 'size', None))
            if outro:
                # Make sure outro matches size and fps before concatenation
                outro = outro.set_fps(FPS_OUTPUT).resize(width=TARGET_RESOLUTION[0], height=TARGET_RESOLUTION[1])
                final_render = concatenate_videoclips([current_video.set_fps(FPS_OUTPUT), outro], method="compose")

            out_file = os.path.join(out_dir, video_filename)
            print(f"ጡ Writing {VIDEO_QUALITY} video with {FPS_OUTPUT} FPS...")
            print(f"ጡ Rendering with DEEP magic colors & optimized codec...")
            final_render.write_videofile(
                out_file, 
                fps=FPS_OUTPUT, 
                codec="libx264", 
                preset='slow',  # Better quality (slower processing)
                bitrate=BITRATE,
                ffmpeg_params=["-crf", "18"],  # Quality level (lower = better, 0-51)
                logger=None
            )
            print(f"✅ Success: {out_file}")
            print(f"✅ Video Quality: {VIDEO_QUALITY} | Resolution: {TARGET_RESOLUTION[0]}x{TARGET_RESOLUTION[1]} | FPS: {FPS_OUTPUT}")
            main_clip.close()
        except Exception as e:
            print(f"❌ Critical Error: {e}")

if __name__ == "__main__":
    run_fast_engine()
