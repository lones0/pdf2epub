import os
import subprocess
import tempfile
import uuid

from flask import Flask, render_template, request, send_file, jsonify

app = Flask(__name__)

MAX_FILE_SIZE_MB = 50
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE_MB * 1024 * 1024


ALLOWED_EXTENSIONS = {".pdf", ".txt", ".docx"}


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

    ext = os.path.splitext(uploaded.filename.lower())[1]
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({"error": "Sadece PDF, TXT veya DOCX dosyası yükleyebilirsin."}), 400

    job_id = uuid.uuid4().hex
    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = os.path.join(tmpdir, f"{job_id}{ext}")
        epub_path = os.path.join(tmpdir, f"{job_id}.epub")
        uploaded.save(input_path)

        cmd = ["ebook-convert", input_path, epub_path]
        if ext == ".txt":
            cmd.extend(["--input-encoding", "utf-8"])
        elif ext == ".pdf":
            cmd.extend(["--linearize-tables"])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=False,
                timeout=300,
            )
        except subprocess.TimeoutExpired:
            return jsonify({"error": "Dönüştürme zaman aşımına uğradı."}), 504

        stdout = result.stdout.decode("utf-8", errors="replace").strip()
        stderr = result.stderr.decode("utf-8", errors="replace").strip()

        if result.returncode != 0 or not os.path.exists(epub_path):
            error_msg = "Dönüştürme başarısız oldu."
            if result.returncode in (-9, 137):
                error_msg = "Sunucu bellek sınırı aşıldı (RAM yetersiz)."
                detail_text = "PDF dosyası çok büyük veya çok fazla görsel içerdiği için Render ücretsiz planının 512 MB bellek sınırı aşıldı."
            else:
                detail_text = stderr or stdout
                if not detail_text:
                    detail_text = f"Calibre bilinmeyen hata kodu ile sonlandı (kod: {result.returncode})."
                elif "password" in detail_text.lower():
                    error_msg = "PDF şifreli veya korumalı."
                elif "permission" in detail_text.lower():
                    error_msg = "PDF kopyalama/dönüştürme izinleri kısıtlı."

            return jsonify({
                "error": error_msg,
                "details": detail_text[-2000:],
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
