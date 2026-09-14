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


def convert_text_to_epub(text_content, epub_path, title="E-Kitap"):
    """Düz metni Calibre ebook-convert kullanarak düşük RAM ile EPUB'a çevirir."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", encoding="utf-8", delete=False) as f:
        f.write(text_content)
        tmp_txt = f.name

    try:
        cmd = [
            "ebook-convert",
            tmp_txt,
            epub_path,
            "--title", title,
            "--input-encoding", "utf-8",
            "--dont-split-on-page-breaks"
        ]
        res = subprocess.run(cmd, capture_output=True, text=False, timeout=300)
        return res.returncode == 0 and os.path.exists(epub_path)
    finally:
        if os.path.exists(tmp_txt):
            os.remove(tmp_txt)


def extract_text_from_pdf(pdf_path):
    """PDF dosyasından sayfa sayfa metin ayıklar (RAM harcamaz)."""
    reader = PdfReader(pdf_path)
    parts = []
    for page in reader.pages:
        txt = page.extract_text()
        if txt:
            parts.append(txt)
    return "\n\n".join(parts)


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

            # Eğer PDF çok büyükse (>100 sayfa veya >10MB), Calibre 512 MB RAM'de çöker.
            # Güvenli ve hızlı metin çıkarıcı hattını doğrudan çalıştır!
            if num_pages > 100 or file_size_mb > 10:
                try:
                    extracted = extract_text_from_pdf(input_path)
                except Exception as e:
                    return jsonify({
                        "error": "PDF metni okunamadı.",
                        "details": str(e)
                    }), 500

                if not extracted.strip():
                    return jsonify({
                        "error": "Bu PDF taranmış görsel (scan) içeriyor.",
                        "details": "PDF içinde seçilebilir dijital metin bulunamadı. Taranmış kitap fotoğrafları OCR olmadan dönüştürülemez."
                    }), 400

                converted_successfully = convert_text_to_epub(extracted, epub_path, title=book_title)

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
                    result = subprocess.run(cmd, capture_output=True, text=False, timeout=300)
                    if result.returncode == 0 and os.path.exists(epub_path):
                        converted_successfully = True
                except subprocess.TimeoutExpired:
                    return jsonify({"error": "Dönüştürme zaman aşımına uğradı."}), 504

                # Doğrudan dönüştürme başarısız olduysa (RAM sınırı vb.), otomatik olarak metin çıkarıcıya geç!
                if not converted_successfully:
                    try:
                        extracted = extract_text_from_pdf(input_path)
                        if extracted.strip():
                            converted_successfully = convert_text_to_epub(extracted, epub_path, title=book_title)
                    except Exception:
                        pass

        elif ext == ".txt":
            with open(input_path, "r", encoding="utf-8", errors="replace") as f:
                txt_content = f.read()
            converted_successfully = convert_text_to_epub(txt_content, epub_path, title=book_title)

        elif ext == ".docx":
            cmd = ["ebook-convert", input_path, epub_path, "--title", book_title]
            res = subprocess.run(cmd, capture_output=True, text=False, timeout=300)
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
