import logging
import os
import statistics
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np

from ai_models.base_detector import BaseDetector
from ai_models.hf_deepfake_client import IMAGE_ENSEMBLE_MODELS, collect_model_scores
from ai_models.pixel_heuristics import analyze_pixel_patterns

logger = logging.getLogger(__name__)

# 프레임 하나를 seek·디코딩하는 비용이 지배적이다. 4K 52초 영상 실측:
# 16장 5.65초 / 8장 3.20초 / 6장 2.08초. 6장이면 10초 영상도 1.7초 간격이라
# 장면 전환을 놓치지 않는다.
MAX_SAMPLED_FRAMES = 6
FRAME_SIZE = (224, 224)

# 샘플링한 프레임을 원본 해상도로 들고 있으면 4K 영상(3420x1962)은 프레임 하나가
# 약 20MB라 16장이면 300MB를 넘는다. 컨테이너에서 워커가 메모리로 죽는다.
#
# 프레임을 쓰는 곳은 셋뿐이고 전부 224x224로 줄여서 본다 — 픽셀 휴리스틱,
# 시간적 일관성, 딥페이크 모델(HF도 서버에서 리사이즈한다). 원본을 유지할
# 이유가 없다. 실측: 원본 594KB 1.18초(score 26.9) → 640px 40KB 0.38초(score 27.7).
FRAME_MAX_SIDE = 640
SUSPICIOUS_FRAME_THRESHOLD = 65

# 프레임 × 모델 수만큼 왕복한다. 전부 동시에 쏘므로 지연은 가장 느린 호출
# 하나에 수렴하지만, 쿼터를 감안해 상한을 둔다(실측 6프레임 × 3모델 = 18콜 3.5초).
MAX_MODEL_FRAMES = 6

# 동시에 떠 있는 추론 요청 수 상한. 위 주석 참고.
MAX_INFLIGHT_CALLS = 6

METHOD_MODEL = "hf-model"
METHOD_ENSEMBLE = "hf-ensemble"
METHOD_HEURISTIC = "local-heuristic"


class VideoDetector(BaseDetector):
    """영상 AI 생성(딥페이크) 판별 모델 (FR-01)

    외부 API 없이 OpenCV로 프레임을 샘플링해 이미지 판별기와 동일한
    픽셀 휴리스틱(노이즈/엣지/색상)을 프레임마다 적용하고,
    프레임 간 변화량으로 시간적 일관성을 추가로 분석한다.
    """

    def detect(self, content):
        capture = cv2.VideoCapture(content)

        if not capture.isOpened():
            capture.release()
            return self._error_result(
                "영상을 열 수 없습니다. 파일이 손상되었거나 지원되지 않는 URL(YouTube/Vimeo 페이지 등)입니다. "
                "직접 링크된 영상 파일(.mp4 등)을 업로드해 주세요."
            )

        try:
            frames = self._sample_frames(capture)
        finally:
            capture.release()

        if not frames:
            return self._error_result("영상에서 분석 가능한 프레임을 추출하지 못했습니다.")

        heuristic_results = []
        for timestamp_sec, frame_bgr in frames:
            frame_rgb = cv2.cvtColor(cv2.resize(frame_bgr, FRAME_SIZE), cv2.COLOR_BGR2RGB)
            analysis = analyze_pixel_patterns(frame_rgb)
            heuristic_results.append({
                "timestamp_sec": timestamp_sec,
                "ai_percent": analysis["ai_percent"],
                "confidence": analysis["confidence"],
            })

        pixel_ai_percent = round(float(np.mean([f["ai_percent"] for f in heuristic_results])), 1)
        temporal = self._analyze_temporal_consistency(frames)

        # 학습 모델을 쓸 수 있으면 그 판정을 주 신호로 삼고, 아니면 휴리스틱으로 돌아간다
        model_results, method, model_name = self._classify_with_model(frames)

        # 집계는 중앙값을 쓴다. 평균은 프레임 하나가 튀면 전체가 끌려간다.
        #
        # 시간적 일관성은 점수에 넣지 않고 참고 문구로만 남긴다. 임계값
        # (std > mean*1.5 → 55점)에 근거가 없어, 지극히 정상인 12초 클립도
        # "합성 경계 의심 55점"을 받았다. 근거 없는 상수가 판정을 흔들면 안 된다.
        if model_results:
            frame_results = model_results
            ai_percent = round(statistics.median(f["ai_percent"] for f in model_results), 1)
        else:
            frame_results = heuristic_results
            ai_percent = round(statistics.median(f["ai_percent"] for f in heuristic_results), 1)

        # 판정이 50%에서 멀수록 확신이 크다고 보고 0~100으로 환산한다(이미지 판별기와 동일 규칙)
        confidence = round(abs(ai_percent - 50) * 2, 1)

        frame_highlights = [
            self._format_timestamp(f["timestamp_sec"])
            for f in frame_results
            if f["ai_percent"] >= SUSPICIOUS_FRAME_THRESHOLD
        ]

        is_deepfake = bool(ai_percent >= 60)

        return {
            "score": ai_percent,
            "details": {
                "is_deepfake": is_deepfake,
                "frame_highlights": frame_highlights,
                "sampled_frames": len(frame_results),
                "pixel_ai_percent": pixel_ai_percent,
                "temporal_consistency": temporal["note"],
                "confidence": confidence,
                # 어떤 방식으로 판정했는지 반드시 노출한다.
                # 휴리스틱 결과를 모델 결과처럼 보이게 하면 안 된다.
                "method": method,
                "model": model_name,
                "summary": self._make_summary(ai_percent, confidence, is_deepfake,
                                              len(frame_results), method, model_name),
            },
        }

    def _classify_with_model(self, frames):
        """프레임을 AI 생성 이미지 탐지 앙상블로 판정한다.

        반환: (프레임별 결과 리스트 또는 None, 사용한 방식, 모델 이름 또는 None)
        토큰이 없거나 전부 실패하면 None을 돌려 호출부가 휴리스틱으로 폴백하게 한다.
        """
        token = os.getenv("HF_TOKEN")
        if not token or not token.strip():
            return None, METHOD_HEURISTIC, None
        token = token.strip()

        # 특정 모델을 지정하면 그것만 쓴다. 앙상블을 우회할 탈출구를 남겨둔다.
        override = os.getenv("HF_DEEPFAKE_MODEL")
        models = (override,) if override else IMAGE_ENSEMBLE_MODELS

        # 프레임 × 모델만큼 왕복하므로 프레임 수에 상한을 둔다
        step = max(1, len(frames) // MAX_MODEL_FRAMES)
        targets = frames[::step][:MAX_MODEL_FRAMES]

        payloads = []
        for timestamp_sec, frame_bgr in targets:
            ok, buffer = cv2.imencode('.jpg', frame_bgr)
            if not ok:
                logger.warning("프레임 JPEG 인코딩 실패", extra={"event": "video.frame.encode_failed"})
                continue
            payloads.append((timestamp_sec, buffer.tobytes()))

        if not payloads:
            return None, METHOD_HEURISTIC, None

        # 순차로 돌면 왕복 대기가 호출 수만큼 곱해진다(실측 8프레임 19.6초 —
        # gunicorn 기본 타임아웃 30초에 걸린다). 그래서 프레임도 동시에 쏜다.
        #
        # 다만 전부 한꺼번에 쏘면 안 된다. 6프레임 × 3모델 = 18개를 동시에 보내면
        # HF가 20초 read timeout을 낸다(실측 18콜 중 2~5개 실패). 콜 하나는
        # 원래 0.5~1.6초다. 모델당 2개 이하로 유지해 폭주를 막는다.
        # 이 메서드는 flask.session이나 db.session을 건드리지 않아 스레드에서 안전하다.
        frame_workers = max(1, MAX_INFLIGHT_CALLS // len(models))
        with ThreadPoolExecutor(max_workers=min(frame_workers, len(payloads))) as pool:
            futures = [
                pool.submit(collect_model_scores, token, models, payload)
                for _, payload in payloads
            ]
            per_frame_scores = [future.result() for future in futures]

        # futures를 제출 순서대로 읽으므로 프레임 순서가 그대로 유지된다.
        # as_completed로 받으면 완료 순서가 섞여 frame_highlights의 시각이 어긋난다.
        results = []
        used_models = {}
        for (timestamp_sec, _), scores in zip(payloads, per_frame_scores):
            if not scores:
                # 이 프레임은 모든 모델이 실패했다. 조용히 0점으로 치지 않고 버린다.
                continue
            used_models.update(dict.fromkeys(scores))
            frame_percent = round(statistics.median(scores.values()), 1)
            results.append({
                "timestamp_sec": timestamp_sec,
                "ai_percent": frame_percent,
                "confidence": round(abs(frame_percent - 50) * 2, 1),
            })

        if not results:
            logger.warning("모든 프레임 판정이 실패해 로컬 휴리스틱으로 폴백합니다",
                           extra={"event": "video.model.fallback"})
            return None, METHOD_HEURISTIC, None

        logger.info("판별 모델로 %d개 프레임 판정 완료", len(results),
                    extra={"event": "video.model.completed"})
        return (
            results,
            METHOD_MODEL if override else METHOD_ENSEMBLE,
            ", ".join(used_models),
        )

    @staticmethod
    def _downscale(frame):
        """긴 변이 FRAME_MAX_SIDE를 넘으면 비율을 유지해 줄인다.

        이미 작은 프레임은 늘리지 않는다. 없는 정보를 만들어내지 않는다.
        """
        height, width = frame.shape[:2]
        longest = max(height, width)
        if longest <= FRAME_MAX_SIDE:
            return frame

        scale = FRAME_MAX_SIDE / longest
        return cv2.resize(
            frame,
            (max(1, int(width * scale)), max(1, int(height * scale))),
            interpolation=cv2.INTER_AREA,
        )

    def _sample_frames(self, capture):
        """영상 전체 구간에서 최대 MAX_SAMPLED_FRAMES개 프레임을 균등 샘플링한다.

        디코딩한 프레임은 즉시 축소해서 보관한다 — FRAME_MAX_SIDE 주석 참고.
        """
        total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = capture.get(cv2.CAP_PROP_FPS) or 0

        frames = []

        if total_frames <= 0 or fps <= 0:
            # 메타데이터를 신뢰할 수 없는 컨테이너(일부 스트리밍 URL 등)는 순차 디코딩으로 대체
            idx = 0
            while len(frames) < MAX_SAMPLED_FRAMES:
                ok, frame = capture.read()
                if not ok:
                    break
                frames.append((idx / (fps or 25.0), self._downscale(frame)))
                idx += 1
            return frames

        sample_count = min(MAX_SAMPLED_FRAMES, total_frames)
        # 구간을 sample_count등분해 각 구간의 가운데를 집는다.
        # linspace(0, total-1)로 끝 프레임을 집으면 seek 후 read가 실패해
        # 요청한 수보다 한 장씩 모자랐다(16 요청 → 15장, 8 요청 → 7장).
        sample_indices = (
            (np.arange(sample_count) + 0.5) * total_frames / sample_count
        ).astype(int)

        for frame_idx in sample_indices:
            capture.set(cv2.CAP_PROP_POS_FRAMES, int(frame_idx))
            ok, frame = capture.read()
            if not ok:
                continue
            frames.append((frame_idx / fps, self._downscale(frame)))

        return frames

    def _analyze_temporal_consistency(self, frames):
        """프레임 간 변화량의 분산으로 딥페이크 특유의 이상 신호를 탐지한다.

        - 변화량이 지나치게 균일(분산이 매우 낮음): 프레임 보간/합성 의심
        - 변화량이 극단적으로 튀는 구간 존재: 얼굴 합성 경계(seam) 의심
        """
        if len(frames) < 2:
            return {"temporal_ai_score": 0.0, "note": "프레임이 부족해 시간적 일관성 분석을 생략했습니다."}

        diffs = []
        prev_gray = None
        for _, frame_bgr in frames:
            gray = cv2.cvtColor(cv2.resize(frame_bgr, FRAME_SIZE), cv2.COLOR_BGR2GRAY).astype(float)
            if prev_gray is not None:
                diffs.append(np.mean(np.abs(gray - prev_gray)))
            prev_gray = gray

        diffs = np.array(diffs)
        mean_diff = float(np.mean(diffs))
        std_diff = float(np.std(diffs))

        if mean_diff < 1.5:
            score = 70.0
            note = "프레임 간 변화가 지나치게 적어 보간/합성이 의심됩니다."
        elif std_diff > mean_diff * 1.5 and mean_diff > 0:
            score = 55.0
            note = "일부 구간에서 급격한 변화가 감지되어 합성 경계가 의심됩니다."
        else:
            score = 15.0
            note = "프레임 간 변화가 자연스러운 범위입니다."

        return {"temporal_ai_score": score, "note": note}

    def _format_timestamp(self, seconds):
        seconds = max(0, int(seconds))
        return f"{seconds // 60:02d}:{seconds % 60:02d}"

    def _make_summary(self, ai_percent, confidence, is_deepfake, sampled_frames,
                      method=METHOD_HEURISTIC, model_name=None):
        if is_deepfake:
            verdict = "AI로 생성·조작된 영상일 가능성이 높습니다"
        elif ai_percent >= 40:
            verdict = "일부 구간에서 이상 신호가 감지되었습니다"
        else:
            verdict = "실제 촬영 영상일 가능성이 높습니다"

        # 판정 방식을 요약문에도 정확히 적는다. details.method만 맞고 문구가
        # 어긋나면, 요약만 읽는 사용자는 여전히 잘못된 정보를 받는다.
        if method in (METHOD_MODEL, METHOD_ENSEMBLE):
            basis = f"프레임 {sampled_frames}개를 AI 생성 탐지 모델({model_name})로 분석"
        else:
            basis = f"프레임 {sampled_frames}개 기준 로컬 픽셀 휴리스틱 분석 (외부 모델 미사용)"

        return f"{verdict} | AI 개입 {ai_percent}% | 신뢰도 {confidence}% | {basis}"

    def _error_result(self, message):
        logger.warning("영상 분석 실패: %s", message)
        return {
            "score": 0.0,
            "details": {
                "is_deepfake": False,
                "frame_highlights": [],
                "error": message,
                "summary": message,
            },
        }
