FROM python:3.12-slim
WORKDIR /srv

COPY shared/ shared/
COPY services/gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/gateway/app/ app/

EXPOSE 8000
CMD ["python", "-m", "app.main"]
