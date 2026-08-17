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

# --timeout: 기본값 30초로는 이미지 다중 업로드가 끝나기 전에 워커가 중단된다.
# HF 모델 호출이 1장당 최대 20초(hf_deepfake_client.py)라 여유를 둔다. 중단되면
# 응답이 JSON이 아니게 되어 프론트가 "서버 응답을 해석할 수 없습니다"를 띄운다.
CMD ["gunicorn", "-b", "0.0.0.0:3000", "-w", "2", "--timeout", "120", "app:app"]
