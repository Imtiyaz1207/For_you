from flask import Flask, render_template, request, jsonify, send_from_directory
from datetime import datetime
import pytz
import requests
import os
import csv
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
import subprocess  # 🔹 for video conversion

app = Flask(__name__)

# Load Google Script URL from .env
load_dotenv()
GOOGLE_SCRIPT_URL = os.getenv("GOOGLE_SCRIPT_URL")

# Log CSV file
LOG_FILE = "logs.csv"
if not os.path.exists(LOG_FILE):
    with open(LOG_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "event", "ip_address", "password_attempt", "result"])

# Indian timezone
india = pytz.timezone('Asia/Kolkata')

# Folder for uploads
UPLOAD_FOLDER = os.path.join("static", "uploads")
ALLOWED_EXTENSIONS = {"mp4", "mov", "avi", "mkv"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def get_client_ip():
    if request.headers.getlist("X-Forwarded-For"):
        ip = request.headers.getlist("X-Forwarded-For")[0].split(',')[0]
    else:
        ip = request.remote_addr
    return ip

def log_event(event, ip, password_attempt="", result=""):
    time_now = datetime.now(india).strftime("%Y-%m-%d %H:%M:%S")
    
    # Log CSV
    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([time_now, event, ip, password_attempt, result])
    
    # Log to Google Sheets
    if GOOGLE_SCRIPT_URL:
        try:
            requests.post(GOOGLE_SCRIPT_URL, json={
                "timestamp": time_now,
                "event": event,
                "ip_address": ip,
                "password_attempt": password_attempt,
                "result": result
            })
        except Exception as e:
            print("Google Sheet logging failed:", e)

# -----------------------------
# Convert video to MP4/H.264
# -----------------------------
def convert_to_h264(input_path, output_path):
    try:
        subprocess.run([
            "ffmpeg", "-y", "-i", input_path,
            "-vcodec", "libx264", "-acodec", "aac",
            "-movflags", "+faststart",
            output_path
        ], check=True)
        return True
    except Exception as e:
        print("Video conversion failed:", e)
        return False

# -----------------------------
# Routes
# -----------------------------
@app.route("/")
def index():
    ip = get_client_ip()
    log_event("page_visit", ip)
    return render_template("index.html", datetime=datetime)

@app.route("/log_action", methods=["POST"])
def log_action():
    data = request.get_json()
    ip = get_client_ip()

    if "password" in data:
        entered_password = data.get("password", "")
        correct_password = "23E51A05C1"
        result = "correct" if entered_password == correct_password else "incorrect"
        log_event("password_attempt", ip, entered_password, result)
        return jsonify({"status": "ok", "result": result})

    elif data.get("action") == "video_button_clicked":
        log_event("video_button_clicked", ip, "", "clicked")
        return jsonify({"status": "ok", "result": "video_click_logged"})
    
    else:
        log_event("unknown_event", ip)
        return jsonify({"status": "ok", "result": "unknown_event"})

@app.route("/upload_story", methods=["POST"])
def upload_story():
    if "video" not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    file = request.files["video"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    if file and allowed_file(file.filename):
        temp_path = os.path.join(app.config["UPLOAD_FOLDER"], "temp_" + secure_filename(file.filename))
        file.save(temp_path)

        final_path = os.path.join(app.config["UPLOAD_FOLDER"], "story.mp4")
        # Convert to H.264/MP4
        if convert_to_h264(temp_path, final_path):
            os.remove(temp_path)  # remove temporary file
            log_event("story_uploaded", get_client_ip(), "", "success")
            return jsonify({"status": "ok", "message": "Story uploaded successfully"})
        else:
            os.remove(temp_path)
            return jsonify({"error": "Video conversion failed"}), 500
    
    return jsonify({"error": "Invalid file type"}), 400

# Serve uploaded video
@app.route("/uploads/<filename>")
def serve_video(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

# -----------------------------
# Run
# -----------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
