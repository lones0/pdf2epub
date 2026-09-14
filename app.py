import os
import subprocess
import tempfile
import uuid

from flask import Flask, render_template, request, send_file, jsonify

app = Flask(__name__)

MAX_FILE_SIZE_MB = 50
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE_MB * 1024 * 1024


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/convert", methods=["POST"])
def convert():
    if "file" not in request.files:
        return jsonify({"error": "Dosya bulunamadı."}), 400

    uploaded = request.files["file"]
    if uploaded.filename == "":
        return jsonify({"error": "Dosya seçilmedi."}), 400

    if not uploaded.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Sadece PDF dosyası yükleyebilirsin."}), 400

    job_id = uuid.uuid4().hex
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, f"{job_id}.pdf")
        epub_path = os.path.join(tmpdir, f"{job_id}.epub")
        uploaded.save(pdf_path)

        try:
            result = subprocess.run(
                ["ebook-convert", pdf_path, epub_path],
                capture_output=True,
                text=True,
                timeout=300,
            )
        except subprocess.TimeoutExpired:
            return jsonify({"error": "Dönüştürme zaman aşımına uğradı."}), 504

        if result.returncode != 0 or not os.path.exists(epub_path):
            return jsonify({
                "error": "Dönüştürme başarısız oldu.",
                "details": result.stderr[-2000:] if result.stderr else "",
            }), 500

        # Read into memory before the temp dir is cleaned up
        with open(epub_path, "rb") as f:
            data = f.read()

    out_name = os.path.splitext(uploaded.filename)[0] + ".epub"
    tmp_out = tempfile.NamedTemporaryFile(delete=False, suffix=".epub")
    tmp_out.write(data)
    tmp_out.close()

    return send_file(
        tmp_out.name,
        as_attachment=True,
        download_name=out_name,
        mimetype="application/epub+zip",
    )


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
