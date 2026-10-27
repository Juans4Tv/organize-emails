FROM python:3.12-slim
WORKDIR /srv

COPY shared/ shared/
COPY services/organizer-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/organizer-service/app/ app/

CMD ["python", "-m", "app.worker"]
