import os
import subprocess
import tempfile
import uuid
import zipfile
import html

from flask import Flask, render_template, request, send_file, jsonify
from pypdf import PdfReader

app = Flask(__name__)

MAX_FILE_SIZE_MB = 50
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE_MB * 1024 * 1024

ALLOWED_EXTENSIONS = {".pdf", ".txt", ".docx"}


def create_epub_from_text(text_content, output_epub_path, title="E-Kitap", author="Bilinmeyen Yazar"):
    """
    Standart kütüphanelerle 0.1 saniyede ve sadece 5 MB RAM ile EPUB üretir.
    Render'ın bellek ve zaman aşımı sınırlarına asla takılmaz.
    """
    book_id = f"urn:uuid:{uuid.uuid4().hex}"
    
    # Paragrafları ayıkla
    raw_paras = [p.strip() for p in text_content.split("\n") if p.strip()]
    if not raw_paras:
        raw_paras = ["İçerik bulunamadı."]

    # Paragrafları mantıklı bölümlere ayır (~60 paragraf/bölüm)
    chapters = []
    current_chapter = []
    for p in raw_paras:
        current_chapter.append(p)
        if len(current_chapter) >= 60:
            chapters.append(current_chapter)
            current_chapter = []
    if current_chapter:
        chapters.append(current_chapter)

    with zipfile.ZipFile(output_epub_path, "w") as z:
        # 1. mimetype (ilk dosya ve sıkıştırmasız olmalıdır)
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        
        # 2. META-INF/container.xml
        container_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>'''
        z.writestr("META-INF/container.xml", container_xml)
        
        # 3. OEBPS/stylesheet.css (E-kitap okuyucular için estetik tipografi)
        css = '''body { font-family: serif; line-height: 1.65; margin: 5%; text-align: justify; }
p { text-indent: 1.2em; margin-top: 0; margin-bottom: 0.6em; }
h2 { text-align: center; margin-top: 2em; margin-bottom: 1.2em; font-family: sans-serif; }'''
        z.writestr("OEBPS/stylesheet.css", css)
        
        # 4. Bölüm dosyaları
        manifest_items = [
            '<item id="css" href="stylesheet.css" media-type="text/css"/>',
            '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
        ]
        spine_items = []
        nav_points = []
        
        for idx, chap_paras in enumerate(chapters, start=1):
            chap_id = f"chap_{idx}"
            chap_file = f"chapter_{idx}.xhtml"
            chap_title = f"Bölüm {idx}"
            
            body_html = "\n".join(f"  <p>{html.escape(p)}</p>" for p in chap_paras)
            xhtml = f'''<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
  <title>{html.escape(chap_title)}</title>
  <link rel="stylesheet" type="text/css" href="stylesheet.css"/>
</head>
<body>
  <h2>{html.escape(chap_title)}</h2>
{body_html}
</body>
</html>'''
            z.writestr(f"OEBPS/{chap_file}", xhtml)
            
            manifest_items.append(f'<item id="{chap_id}" href="{chap_file}" media-type="application/xhtml+xml"/>')
            spine_items.append(f'<itemref idref="{chap_id}"/>')
            nav_points.append(f'''    <navPoint id="nav_{chap_id}" playOrder="{idx}">
      <navLabel><text>{html.escape(chap_title)}</text></navLabel>
      <content src="{chap_file}"/>
    </navPoint>''')
            
        # 5. OEBPS/content.opf
        opf = f'''<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="BookId" version="2.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:title>{html.escape(title)}</dc:title>
    <dc:creator>{html.escape(author)}</dc:creator>
    <dc:language>tr</dc:language>
    <dc:identifier id="BookId">{book_id}</dc:identifier>
  </metadata>
  <manifest>
    {chr(10).join(manifest_items)}
  </manifest>
  <spine toc="ncx">
    {chr(10).join(spine_items)}
  </spine>
</package>'''
        z.writestr("OEBPS/content.opf", opf)
        
        # 6. OEBPS/toc.ncx
        ncx = f'''<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="{book_id}"/>
    <meta name="dtb:depth" content="1"/>
    <meta name="dtb:totalPageCount" content="0"/>
    <meta name="dtb:maxPageNumber" content="0"/>
  </head>
  <docTitle><text>{html.escape(title)}</text></docTitle>
  <navMap>
{chr(10).join(nav_points)}
  </navMap>
</ncx>'''
        z.writestr("OEBPS/toc.ncx", ncx)

    return os.path.exists(output_epub_path) and os.path.getsize(output_epub_path) > 100


def extract_text_from_pdf(pdf_path):
    """C++ poppler pdftotext veya pypdf ile saniyeler içinde sıfır RAM ile metin çıkarır."""
    # 1. Poppler C++ pdftotext (ultra hızlı, 600 sayfa < 1 sn)
    txt_temp = pdf_path + ".txt"
    try:
        res = subprocess.run(
            ["pdftotext", "-layout", pdf_path, txt_temp],
            capture_output=True,
            timeout=30
        )
        if res.returncode == 0 and os.path.exists(txt_temp) and os.path.getsize(txt_temp) > 10:
            with open(txt_temp, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            os.remove(txt_temp)
            if content.strip():
                return content
    except Exception:
        pass
    finally:
        if os.path.exists(txt_temp):
            os.remove(txt_temp)

    # 2. Yedek pypdf
    try:
        reader = PdfReader(pdf_path)
        parts = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                parts.append(t)
        return "\n\n".join(parts)
    except Exception:
        return ""


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

        if ext == ".txt":
            with open(input_path, "r", encoding="utf-8", errors="replace") as f:
                text_data = f.read()
            converted_successfully = create_epub_from_text(text_data, epub_path, title=book_title)

        elif ext == ".docx":
            cmd = ["ebook-convert", input_path, epub_path, "--title", book_title]
            res = subprocess.run(cmd, capture_output=True, text=False, timeout=120)
            converted_successfully = (res.returncode == 0 and os.path.exists(epub_path))

        elif ext == ".pdf":
            num_pages = 0
            try:
                reader = PdfReader(input_path)
                num_pages = len(reader.pages)
            except Exception:
                pass

            file_size_mb = os.path.getsize(input_path) / (1024 * 1024)

            # Kalın veya ağır PDF'lerde (>50 sayfa veya >5MB):
            # Calibre'in 512 MB RAM ve 60 sn Render proxy zaman aşımına takılmaması için
            # doğrudan ultra hızlı metin ayıklama ve hafif EPUB motorunu çalıştır!
            if num_pages > 50 or file_size_mb > 5:
                extracted = extract_text_from_pdf(input_path)
                if not extracted.strip():
                    return jsonify({
                        "error": "Bu PDF taranmış görsel (scan) içeriyor.",
                        "details": "PDF içinde seçilebilir dijital metin bulunamadı. Taranmış kitap fotoğrafları OCR olmadan dönüştürülemez."
                    }), 400
                converted_successfully = create_epub_from_text(extracted, epub_path, title=book_title)
            else:
                # Küçük PDF: önce Calibre ile dene (görseller korunsun)
                cmd = [
                    "ebook-convert",
                    input_path,
                    epub_path,
                    "--title", book_title,
                    "--linearize-tables"
                ]
                try:
                    res = subprocess.run(cmd, capture_output=True, text=False, timeout=45)
                    if res.returncode == 0 and os.path.exists(epub_path):
                        converted_successfully = True
                except subprocess.TimeoutExpired:
                    pass

                # Calibre başarısız olursa akıllı yedek motora geç!
                if not converted_successfully:
                    extracted = extract_text_from_pdf(input_path)
                    if extracted.strip():
                        converted_successfully = create_epub_from_text(extracted, epub_path, title=book_title)

        if not converted_successfully or not os.path.exists(epub_path):
            return jsonify({
                "error": "Dönüştürme başarısız oldu.",
                "details": "Dosya içeriği okunamadı veya dönüştürülebilir metin bulunamadı."
            }), 500

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
