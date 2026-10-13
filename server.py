
import os
import re
import shutil
import tempfile
import urllib.request

from flask import Flask, request, send_file, jsonify
import yt_dlp

app = Flask(__name__)


@app.route("/")
def home():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Linkpour</title>
    </head>
    <body style="font-family:Arial,sans-serif;text-align:center;padding:50px">
        <h1>Welcome to Linkpour 🚀</h1>
        <p>Your backend is running successfully!</p>
    </body>
    </html>
    """


@app.after_request
def cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Expose-Headers"] = "Content-Disposition"
    resp.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp


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
            postprocessors=[{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
        )

    else:
        base.update(format="best")

    return base


def download_image(url, outdir):
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0"}
    )

    with urllib.request.urlopen(req, timeout=20) as response:
        html = response.read().decode("utf-8", "ignore")

    match = re.search(
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
        html,
        re.IGNORECASE,
    )

    if not match:
        raise RuntimeError("No image found")

    img_url = match.group(1).replace("&amp;", "&")
    path = os.path.join(outdir, "image.jpg")

    req = urllib.request.Request(
        img_url, headers={"User-Agent": "Mozilla/5.0"}
    )

    with urllib.request.urlopen(req, timeout=30) as response:
        with open(path, "wb") as file:
            shutil.copyfileobj(response, file)

    return path


@app.route("/health")
def health():
    return jsonify(ok=True)


@app.route("/download", methods=["GET", "OPTIONS"])
def download():
    if request.method == "OPTIONS":
        return "", 204

    url = request.args.get("url", "").strip()
    fmt = request.args.get("format", "v720")

    if not url.startswith(("http://", "https://")):
        return jsonify(error="Invalid link"), 400

    allowed_formats = {"v1080", "v720", "v360", "a192", "img"}
    if fmt not in allowed_formats:
        return jsonify(error="Unsupported format"), 400

    outdir = tempfile.mkdtemp(prefix="linkpour_")

    try:
        try:
            with yt_dlp.YoutubeDL(options(fmt, outdir)) as ydl:
                ydl.download([url])

            files = [
                name for name in os.listdir(outdir)
                if os.path.isfile(os.path.join(outdir, name))
            ]

            if not files:
                raise RuntimeError("Nothing downloaded")

            path = os.path.join(outdir, files[0])

        except Exception:
            if fmt != "img":
                raise

            path = download_image(url, outdir)

        response = send_file(
            path,
            as_attachment=True,
            download_name=os.path.basename(path),
        )

        response.call_on_close(
            lambda: shutil.rmtree(outdir, ignore_errors=True)
        )
        return response

    except Exception as error:
        shutil.rmtree(outdir, ignore_errors=True)
        app.logger.exception("Download failed: %s", error)

        return jsonify(error="Could not download that link"), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
