FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libtesseract-dev \
    libleptonica-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY . /app

RUN pip install --no-cache-dir -r requirements.txt

ENV BOT_TOKEN="" \
    ADMIN_ID="" \
    NEQUI_NUMBER=""

CMD ["python", "Completofinal1.py"]
