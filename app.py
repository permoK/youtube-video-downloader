from flask import Flask, render_template, request, jsonify, send_file, render_template_string
import yt_dlp
import os
import tempfile
import logging
from datetime import timedelta
import re

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# Create a temporary directory for downloads
TEMP_DIR = tempfile.mkdtemp()

def format_duration(seconds):
    if not seconds:
        return "Unknown duration"
    return str(timedelta(seconds=seconds))

def clean_filename(title):
    # Remove invalid filename characters
    cleaned = re.sub(r'[<>:"/\\|?*]', '', title)
    # Limit length and remove trailing spaces
    return cleaned[:100].strip()

@app.route('/')
def home():
    with open('templates/index.html', 'r', encoding='utf-8') as file:
        template_content = file.read()
    return render_template_string(template_content)

@app.route('/api/info', methods=['POST'])
def get_info():
    try:
        data = request.get_json()
        url = data.get('url')
        
        if not url:
            return jsonify({'error': 'No URL provided'}), 400

        # Configure yt-dlp options for info extraction
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
                
                # Extract and format video information
                video_info = {
                    'title': info.get('title', 'Unknown Title'),
                    'duration': format_duration(info.get('duration')),
                    'thumbnail': info.get('thumbnail', ''),
                }
                
                return jsonify(video_info)
            
            except Exception as e:
                logging.error(f"Error extracting video info: {str(e)}")
                return jsonify({'error': 'Invalid YouTube URL or video not found'}), 400

    except Exception as e:
        logging.error(f"Server error: {str(e)}")
        return jsonify({'error': 'Server error occurred'}), 500

@app.route('/api/download', methods=['POST'])
def download_video():
    try:
        data = request.get_json()
        url = data.get('url')
        quality = data.get('quality', 'highest')
        
        if not url:
            return jsonify({'error': 'No URL provided'}), 400

        # Map quality selection to yt-dlp format
        format_selection = {
            'highest': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            '720p': 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best',
            '480p': 'bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]/best',
            '360p': 'bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360][ext=mp4]/best'
        }.get(quality, 'best[ext=mp4]')

        # Configure download options
        ydl_opts = {
            'format': format_selection,
            'outtmpl': os.path.join(TEMP_DIR, '%(title)s.%(ext)s'),
            'merge_output_format': 'mp4',
            'restrictfilenames': True,
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Extract info first to get the filename
            info = ydl.extract_info(url, download=False)
            title = clean_filename(info.get('title', 'video'))
            
            # Download the video
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            if not os.path.exists(filename):
                # If the file doesn't exist with .mp4 extension, try to find it
                base_path = os.path.splitext(filename)[0]
                potential_files = [f for f in os.listdir(TEMP_DIR) if f.startswith(os.path.basename(base_path))]
                if potential_files:
                    filename = os.path.join(TEMP_DIR, potential_files[0])
                else:
                    raise Exception("Downloaded file not found")

            # Send the file to the user
            try:
                return send_file(
                    filename,
                    as_attachment=True,
                    download_name=f"{title}.mp4",
                    mimetype='video/mp4'
                )
            finally:
                # Clean up the file after sending
                try:
                    os.remove(filename)
                except:
                    pass

    except Exception as e:
        logging.error(f"Download error: {str(e)}")
        return jsonify({'error': str(e)}), 500

def cleanup_old_files():
    """Clean up old files in the temp directory"""
    try:
        for filename in os.listdir(TEMP_DIR):
            filepath = os.path.join(TEMP_DIR, filename)
            try:
                if os.path.isfile(filepath):
                    os.remove(filepath)
            except:
                pass
    except:
        pass

@app.before_request
def before_request():
    cleanup_old_files()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5200, debug=True)
