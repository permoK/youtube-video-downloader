from flask import Flask, render_template, request, jsonify, send_file, render_template_string, send_from_directory
from flask_socketio import SocketIO, emit
import yt_dlp
import os
import tempfile
import logging
import time
from datetime import timedelta
import re
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)
socketio = SocketIO(app)
logging.basicConfig(level=logging.INFO)

TEMP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'downloads')
if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR)

executor = ThreadPoolExecutor(max_workers=4)

class ProgressHook:
    def __init__(self, socket_id):
        self.socket_id = socket_id
        self.downloaded = 0
        self.total = 0

    def __call__(self, d):
        if d['status'] == 'downloading':
            self.downloaded = d.get('downloaded_bytes', 0)
            self.total = d.get('total_bytes', 0) or d.get('total_bytes_estimate', 0)
            
            if self.total > 0:
                progress = (self.downloaded / self.total) * 100
                socketio.emit('download_progress', {
                    'progress': progress,
                    'socket_id': self.socket_id
                })

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

@app.route('/downloads/<path:filename>')
def download_file(filename):
    return send_from_directory(TEMP_DIR, filename, as_attachment=True)

@socketio.on('start_download')
def handle_download(data):
    try:
        url = data.get('url')
        format_type = data.get('format', 'mp4')
        socket_id = request.sid
        
        if not url:
            emit('download_error', {'error': 'No URL provided'})
            return

        format_config = {
            'mp4': 'best[ext=mp4]/best',
            'mp3': 'bestaudio[ext=mp3]/bestaudio',
            'm4a': 'bestaudio[ext=m4a]/bestaudio'
        }

        ydl_opts = {
            'format': format_config.get(format_type, 'best'),
            'outtmpl': os.path.join(TEMP_DIR, '%(title)s.%(ext)s'),
            'restrictfilenames': True,
            'noplaylist': True,
            'quiet': True,
            'progress_hooks': [ProgressHook(socket_id)]
        }

        if format_type in ['mp3', 'm4a']:
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': format_type,
                'preferredquality': '128',
            }]

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            if format_type in ['mp3', 'm4a']:
                base = os.path.splitext(filename)[0]
                filename = f"{base}.{format_type}"

            if os.path.exists(filename):
                emit('download_complete', {'filename': os.path.basename(filename)})
            else:
                emit('download_error', {'error': 'File not found after download'})

    except Exception as e:
        logging.error(f"Download error: {str(e)}")
        emit('download_error', {'error': str(e)})

def cleanup_old_files():
    try:
        for filename in os.listdir(TEMP_DIR):
            filepath = os.path.join(TEMP_DIR, filename)
            if os.path.isfile(filepath) and os.path.getctime(filepath) < time.time() - 3600:
                try:
                    os.remove(filepath)
                except:
                    pass
    except Exception as e:
        logging.error(f"Cleanup error: {str(e)}")

@app.before_request
def before_request():
    cleanup_old_files()

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5200, debug=True)
