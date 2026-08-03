FROM python:3.11-slim

WORKDIR /app

# opencv-python-headless(OpenCV) 실행에 필요한 최소 시스템 라이브러리
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# cloudtype 등 non-root 런타임에서도 쓰기 가능하도록 권한 개방
RUN mkdir -p uploads instance && chmod -R 777 uploads instance

EXPOSE 3000

CMD ["gunicorn", "-b", "0.0.0.0:3000", "-w", "2", "app:app"]
