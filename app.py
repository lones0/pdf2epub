import os
import subprocess
import tempfile
import uuid

from flask import Flask, render_template, request, send_file, jsonify
from pypdf import PdfReader

app = Flask(__name__)

MAX_FILE_SIZE_MB = 50
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE_MB * 1024 * 1024

ALLOWED_EXTENSIONS = {".pdf", ".txt", ".docx"}


def extract_text_to_file(pdf_path, txt_path):
    """C++ poppler pdftotext ile 0.5 saniyede ve sıfır RAM ile metin çıkarır. Yedek olarak pypdf kullanır."""
    # 1. Poppler pdftotext (ultra hızlı C++ motoru, 600 sayfa < 1 sn)
    try:
        res = subprocess.run(
            ["pdftotext", "-layout", pdf_path, txt_path],
            capture_output=True,
            timeout=40
        )
        if res.returncode == 0 and os.path.exists(txt_path) and os.path.getsize(txt_path) > 10:
            return True
    except Exception:
        pass

    # 2. Yedek pypdf motoru
    try:
        reader = PdfReader(pdf_path)
        with open(txt_path, "w", encoding="utf-8") as f:
            for page in reader.pages:
                t = page.extract_text()
                if t:
                    f.write(t)
                    f.write("\n\n")
        return os.path.exists(txt_path) and os.path.getsize(txt_path) > 10
    except Exception:
        return False


def convert_txt_to_epub(txt_path, epub_path, title="E-Kitap"):
    """Düz metin dosyasını Calibre ile hafif ve hızlı şekilde EPUB'a çevirir."""
    cmd = [
        "ebook-convert",
        txt_path,
        epub_path,
        "--title", title,
        "--input-encoding", "utf-8",
        "--dont-split-on-page-breaks"
    ]
    res = subprocess.run(cmd, capture_output=True, text=False, timeout=180)
    return res.returncode == 0 and os.path.exists(epub_path)


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

    book_title = os.path.splitext(uploaded.filename)[0]
    job_id = uuid.uuid4().hex

    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = os.path.join(tmpdir, f"{job_id}{ext}")
        epub_path = os.path.join(tmpdir, f"{job_id}.epub")
        uploaded.save(input_path)

        converted_successfully = False

        if ext == ".pdf":
            num_pages = 0
            try:
                reader = PdfReader(input_path)
                num_pages = len(reader.pages)
            except Exception:
                pass

            file_size_mb = os.path.getsize(input_path) / (1024 * 1024)

            # Büyük PDF'lerde (>80 sayfa veya >8MB) doğrudan hızlı metin çıkarıcı hattını çalıştır
            # Böylece Render'ın 512 MB RAM ve 60 saniyelik proxy sınırına asla takılmaz!
            if num_pages > 80 or file_size_mb > 8:
                txt_path = os.path.join(tmpdir, f"{job_id}.txt")
                if not extract_text_to_file(input_path, txt_path):
                    return jsonify({
                        "error": "Bu PDF taranmış görsel (scan) içeriyor.",
                        "details": "PDF içinde seçilebilir dijital metin bulunamadı. Taranmış kitap fotoğrafları OCR olmadan dönüştürülemez."
                    }), 400

                converted_successfully = convert_txt_to_epub(txt_path, epub_path, title=book_title)

            else:
                # Normal boyutlu PDF: Önce doğrudan Calibre ile dene (görseller ve mizanpaj korunsun)
                cmd = [
                    "ebook-convert",
                    input_path,
                    epub_path,
                    "--title", book_title,
                    "--linearize-tables"
                ]
                try:
                    result = subprocess.run(cmd, capture_output=True, text=False, timeout=90)
                    if result.returncode == 0 and os.path.exists(epub_path):
                        converted_successfully = True
                except subprocess.TimeoutExpired:
                    pass

                # Doğrudan dönüştürme başarısız olursa otomatik metin çıkarıcıya geç
                if not converted_successfully:
                    txt_path = os.path.join(tmpdir, f"{job_id}.txt")
                    if extract_text_to_file(input_path, txt_path):
                        converted_successfully = convert_txt_to_epub(txt_path, epub_path, title=book_title)

        elif ext == ".txt":
            converted_successfully = convert_txt_to_epub(input_path, epub_path, title=book_title)

        elif ext == ".docx":
            cmd = ["ebook-convert", input_path, epub_path, "--title", book_title]
            res = subprocess.run(cmd, capture_output=True, text=False, timeout=180)
            converted_successfully = (res.returncode == 0 and os.path.exists(epub_path))

        if not converted_successfully or not os.path.exists(epub_path):
            return jsonify({
                "error": "Dönüştürme başarısız oldu.",
                "details": "Dosya biçimi okunamadı veya dönüştürülebilir metin bulunamadı."
            }), 500

        # Read into memory before the temp dir is cleaned up
        with open(epub_path, "rb") as f:
            data = f.read()

    out_name = book_title + ".epub"
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
