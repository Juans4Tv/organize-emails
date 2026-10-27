FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-spa \
    && rm -rf /var/lib/apt/lists/*

ENV TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata

WORKDIR /srv

COPY shared/ shared/
COPY services/pdf-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/pdf-service/app/ app/

CMD ["python", "-m", "app.worker"]
