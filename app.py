from flask import Flask, render_template, request, send_file
import yt_dlp
import os
import tempfile
import logging
import re

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# Create a temporary directory for downloads
TEMP_DIR = tempfile.mkdtemp()

@app.route('/', methods=['GET', 'POST'])
def home():
    message = None
    if request.method == 'POST':
        try:
            # Get YouTube URL from form
            yt_url = request.form['url']
            
            # Validate YouTube URL
            if not re.match(r'^(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+$', yt_url):
                raise ValueError("Invalid YouTube URL")
            
            # Configure yt-dlp options
            ydl_opts = {
                'format': 'best',  # Download best quality
                'outtmpl': os.path.join(TEMP_DIR, '%(title)s.%(ext)s'),
                'restrictfilenames': True,  # Restrict filenames to ASCII
                'noplaylist': True,  # Download single video only
            }
            
            # Download the video
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(yt_url, download=True)
                filename = ydl.prepare_filename(info)
            
            # Return the file to user
            return send_file(
                filename,
                as_attachment=True,
                download_name=os.path.basename(filename)
            )
            
        except ValueError as ve:
            message = str(ve)
            logging.error(f"Validation error: {str(ve)}")
        except Exception as e:
            message = f"An error occurred: {str(e)}"
            logging.error(f"Download error: {str(e)}")
    
    return render_template('index.html', message=message)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5200, debug=True)
