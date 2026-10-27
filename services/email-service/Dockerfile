FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libarchive-tools \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

COPY shared/ shared/
COPY services/email-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/email-service/app/ app/

CMD ["python", "-m", "app.main"]
