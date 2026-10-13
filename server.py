"""
Linkpour server - runs on YOUR computer so linkpour.html can download real files.

Setup (one time):
    pip install flask yt-dlp
    (and install ffmpeg - needed for MP4 merging and MP3)

Run:
    python server.py

Leave this window open, then open linkpour.html from your computer.
Use it only for videos/audio/photos you own or have permission to save.
"""
import os, re, shutil, tempfile, urllib.request
from flask import Flask, request, send_file, jsonify
import yt_dlp

app = Flask(__name__)

# the page opens as a local file, so it needs permission to talk to this server
@app.after_request
def cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Expose-Headers"] = "Content-Disposition"
    return resp

# format ids used by linkpour.html -> yt-dlp settings
def options(fmt, outdir):
    base = {
        "outtmpl": os.path.join(outdir, "%(title).80s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "restrictfilenames": False,
    }
    heights = {"v1080": 1080, "v720": 720, "v360": 360}
    if fmt in heights:
        h = heights[fmt]
        base.update(
            format=f"bestvideo[height<={h}]+bestaudio/best[height<={h}]/best",
            merge_output_format="mp4",
        )
    elif fmt == "a192":
        base.update(
            format="bestaudio/best",
            postprocessors=[{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}],
        )
    else:  # "img" or anything else: best available
        base.update(format="best")
    return base

# photo pins: grab the page's main image if yt-dlp finds no video
def download_image(url, outdir):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    html = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore")
    m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', html)
    if not m:
        raise RuntimeError("No image found")
    img_url = m.group(1).replace("&amp;", "&")
    path = os.path.join(outdir, "image.jpg")
    req = urllib.request.Request(img_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r, open(path, "wb") as f:
        shutil.copyfileobj(r, f)
    return path

@app.route("/health")
def health():
    return jsonify(ok=True)

@app.route("/download")
def download():
    url = request.args.get("url", "").strip()
    fmt = request.args.get("format", "v720")
    if not url.startswith(("http://", "https://")):
        return jsonify(error="Invalid link"), 400

    outdir = tempfile.mkdtemp(prefix="linkpour_")
    try:
        try:
            with yt_dlp.YoutubeDL(options(fmt, outdir)) as ydl:
                ydl.download([url])
            files = os.listdir(outdir)
            if not files:
                raise RuntimeError("Nothing downloaded")
            path = os.path.join(outdir, files[0])
        except Exception:
            if fmt != "img":
                raise
            path = download_image(url, outdir)
        resp = send_file(path, as_attachment=True, download_name=os.path.basename(path))
        resp.call_on_close(lambda: shutil.rmtree(outdir, ignore_errors=True))
        return resp
    except Exception as e:
        shutil.rmtree(outdir, ignore_errors=True)
        print("Download failed:", e)
        return jsonify(error="Could not download that link"), 500

if __name__ == "__main__":
    print("Linkpour server running on http://localhost:5000  (keep this window open)")
    app.run(host="127.0.0.1", port=5000)
