from flask import Flask, render_template, request, jsonify, send_file, render_template_string
import yt_dlp
import os
import tempfile
import logging
from datetime import timedelta
import re
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# Create a temporary directory for downloads
TEMP_DIR = tempfile.mkdtemp()
# Create a thread pool for concurrent downloads
executor = ThreadPoolExecutor(max_workers=4)

def format_duration(seconds):
    if not seconds:
        return "Unknown duration"
    return str(timedelta(seconds=seconds))

def clean_filename(title):
    cleaned = re.sub(r'[<>:"/\\|?*]', '', title)
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

        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
                
                # Enhanced video information
                video_info = {
                    'title': info.get('title', 'Unknown Title'),
                    'duration': format_duration(info.get('duration')),
                    'thumbnail': info.get('thumbnail', ''),
                    'formats': [
                        {'ext': 'mp4', 'label': 'Video (MP4)'},
                        {'ext': 'mp3', 'label': 'Audio (MP3)'},
                        {'ext': 'm4a', 'label': 'Audio (M4A)'}
                    ]
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
        format_type = data.get('format', 'mp4')
        
        if not url:
            return jsonify({'error': 'No URL provided'}), 400

        # Enhanced format selection with audio support
        format_selection = {
            'mp4': {
                'highest': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                '720p': 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best',
                '480p': 'bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]/best',
                '360p': 'bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360][ext=mp4]/best'
            },
            'mp3': {
                'highest': 'bestaudio[ext=mp3]/bestaudio/best',
                '128k': 'bestaudio[abr<=128]/best[abr<=128]/best',
                '96k': 'bestaudio[abr<=96]/best[abr<=96]/best',
                '64k': 'bestaudio[abr<=64]/best[abr<=64]/best'
            },
            'm4a': {
                'highest': 'bestaudio[ext=m4a]/bestaudio/best',
                '128k': 'bestaudio[abr<=128][ext=m4a]/best[abr<=128]/best',
                '96k': 'bestaudio[abr<=96][ext=m4a]/best[abr<=96]/best',
                '64k': 'bestaudio[abr<=64][ext=m4a]/best[abr<=64]/best'
            }
        }

        # Configure optimized download options
        ydl_opts = {
            'format': format_selection[format_type][quality],
            'outtmpl': os.path.join(TEMP_DIR, '%(title)s.%(ext)s'),
            'restrictfilenames': True,
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'postprocessors': [],
            'concurrent_fragment_downloads': 10,  # Enable parallel fragment downloads
            'buffersize': 1024 * 1024,  # Increase buffer size to 1MB
        }

        # Add format-specific options
        if format_type == 'mp3':
            ydl_opts['postprocessors'].append({
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': quality.replace('k', ''),
            })
            ydl_opts['format'] = 'bestaudio/best'
        elif format_type == 'm4a':
            ydl_opts['postprocessors'].append({
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'm4a',
                'preferredquality': quality.replace('k', ''),
            })
            ydl_opts['format'] = 'bestaudio/best'

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Extract info first to get the filename
            info = ydl.extract_info(url, download=False)
            title = clean_filename(info.get('title', 'video'))
            
            # Download the video/audio using thread pool
            info = executor.submit(ydl.extract_info, url, download=True).result()
            filename = ydl.prepare_filename(info)
            
            # Handle different output extensions
            if format_type in ['mp3', 'm4a']:
                base_path = os.path.splitext(filename)[0]
                filename = f"{base_path}.{format_type}"

            if not os.path.exists(filename):
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
                    download_name=f"{title}.{format_type}",
                    mimetype=f'{"video" if format_type == "mp4" else "audio"}/{format_type}'
                )
            finally:
                try:
                    os.remove(filename)
                except:
                    pass

    except Exception as e:
        logging.error(f"Download error: {str(e)}")
        return jsonify({'error': str(e)}), 500

def cleanup_old_files():
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
