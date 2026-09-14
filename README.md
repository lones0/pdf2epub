# PDF → EPUB Dönüştürücü

Basit bir web uygulaması: PDF yükle, Calibre ile EPUB'a çevir, indir. Mobil tarayıcıdan (Chrome/Safari) sorunsuz çalışır — arkadaşının kurulum yapmasına gerek yok, sadece linki açması yeterli.

## Render'a ücretsiz deploy (önerilen yol)

1. Bu klasörü bir GitHub reposuna yükle (public ya da private, fark etmez).
2. [render.com](https://render.com) üzerinde ücretsiz hesap aç.
3. "New +" → "Web Service" → GitHub reponu bağla.
4. Render, klasördeki `render.yaml` dosyasını otomatik algılar (Docker tabanlı olduğunu görür). Algılamazsa manuel olarak:
   - **Environment:** Docker
   - **Plan:** Free
5. "Create Web Service" de tıkla. İlk build 5-10 dakika sürebilir (Calibre kurulumu ağır).
6. Build bitince Render sana `https://pdf2epub-xxxx.onrender.com` gibi bir link verir. Bu linki arkadaşınla paylaş.

**Not:** Render'ın ücretsiz planı, 15 dakika istek gelmezse uygulamayı uyutur. İlk açılışta 30-50 saniye "uyanma" süresi olabilir — normaldir, arkadaşına söyleyebilirsin.

## Yerelde test etmek istersen

```bash
docker build -t pdf2epub .
docker run -p 5000:5000 pdf2epub
```

Sonra tarayıcıdan `http://localhost:5000` adresini aç.

## Sınırlamalar

- Maksimum dosya boyutu 50 MB (app.py içindeki `MAX_FILE_SIZE_MB` değerinden değiştirebilirsin).
- Taranmış (scan) / görsel ağırlıklı PDF'lerde çıktı kalitesi düşük olabilir — Calibre'in OCR desteği yok, bu tür dosyalar için ayrı bir OCR adımı gerekir.
- Çok büyük/karmaşık PDF'lerde dönüştürme birkaç dakika sürebilir; timeout 300 saniyeye ayarlı.
