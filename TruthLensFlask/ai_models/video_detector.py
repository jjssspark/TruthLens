import logging
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np

from ai_models.base_detector import BaseDetector
from ai_models.hf_deepfake_client import HFDeepfakeClient, HFInferenceError
from ai_models.pixel_heuristics import analyze_pixel_patterns

logger = logging.getLogger(__name__)

MAX_SAMPLED_FRAMES = 16
FRAME_SIZE = (224, 224)
SUSPICIOUS_FRAME_THRESHOLD = 65

# 모델 호출은 프레임당 1회 왕복이라 지연·쿼터를 감안해 더 적게 쓴다
MAX_MODEL_FRAMES = 8

METHOD_MODEL = "hf-model"
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

        if model_results:
            frame_results = model_results
            primary_percent = round(float(np.mean([f["ai_percent"] for f in model_results])), 1)
            # 모델 판정 80% + 시간적 일관성 20%
            ai_percent = round(primary_percent * 0.8 + temporal["temporal_ai_score"] * 0.2, 1)
            confidence = round(float(np.mean([f["confidence"] for f in model_results])), 1)
        else:
            frame_results = heuristic_results
            # 프레임 평균 픽셀 휴리스틱 70% + 시간적 일관성 이상 신호 30%
            ai_percent = round(pixel_ai_percent * 0.7 + temporal["temporal_ai_score"] * 0.3, 1)
            confidence = round(float(np.mean([f["confidence"] for f in heuristic_results])), 1)

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
        """학습된 딥페이크 모델로 프레임을 판정한다.

        반환: (프레임별 결과 리스트 또는 None, 사용한 방식, 모델 이름 또는 None)
        토큰이 없거나 호출이 실패하면 None을 돌려 호출부가 휴리스틱으로 폴백하게 한다.
        """
        client = HFDeepfakeClient.from_env()
        if client is None:
            return None, METHOD_HEURISTIC, None

        # 프레임당 1회 왕복이므로 균등 간격으로 솎아낸다
        step = max(1, len(frames) // MAX_MODEL_FRAMES)
        targets = frames[::step][:MAX_MODEL_FRAMES]

        payloads = []
        for timestamp_sec, frame_bgr in targets:
            ok, buffer = cv2.imencode('.jpg', frame_bgr)
            if not ok:
                logger.warning("프레임 JPEG 인코딩 실패", extra={"event": "video.frame.encode_failed"})
                continue
            payloads.append((timestamp_sec, buffer.tobytes()))

        # 프레임마다 왕복 1회라 순차로 돌면 대기가 프레임 수만큼 곱해진다
        # (실측 8프레임 19.6초 — gunicorn 기본 타임아웃 30초에 걸린다). 동시에 쏜다.
        # 이 메서드는 flask.session이나 db.session을 건드리지 않아 스레드에서 안전하다.
        with ThreadPoolExecutor(max_workers=len(payloads) or 1) as pool:
            futures = [pool.submit(client.fake_percent, payload) for _, payload in payloads]

            scores = []
            for future in futures:
                try:
                    scores.append(future.result())
                except HFInferenceError as e:
                    # 한 프레임이라도 실패하면 통째로 휴리스틱으로 돌아간다.
                    # 일부만 모델 판정인 혼합 결과는 해석할 수 없다.
                    logger.warning("딥페이크 모델 호출 실패, 로컬 휴리스틱으로 폴백합니다: %s", e,
                                   extra={"event": "video.model.fallback"})
                    return None, METHOD_HEURISTIC, None

        # futures를 제출 순서대로 읽으므로 프레임 순서가 그대로 유지된다.
        # as_completed로 받으면 완료 순서가 섞여 frame_highlights의 시각이 어긋난다.
        results = [
            {
                "timestamp_sec": timestamp_sec,
                "ai_percent": fake_percent,
                # 모델은 프레임별 신뢰도를 따로 주지 않는다. 판정이 0.5에서
                # 멀수록 확신이 크다고 보고 0~100으로 환산한다.
                "confidence": round(abs(fake_percent - 50) * 2, 1),
            }
            for (timestamp_sec, _), fake_percent in zip(payloads, scores)
        ]

        if not results:
            return None, METHOD_HEURISTIC, None

        logger.info("딥페이크 모델로 %d개 프레임 판정 완료", len(results),
                    extra={"event": "video.model.completed"})
        return results, METHOD_MODEL, client.model

    def _sample_frames(self, capture):
        """영상 전체 구간에서 최대 MAX_SAMPLED_FRAMES개 프레임을 균등 샘플링한다."""
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
                frames.append((idx / (fps or 25.0), frame))
                idx += 1
            return frames

        sample_count = min(MAX_SAMPLED_FRAMES, total_frames)
        sample_indices = np.linspace(0, total_frames - 1, num=sample_count, dtype=int)

        for frame_idx in sample_indices:
            capture.set(cv2.CAP_PROP_POS_FRAMES, int(frame_idx))
            ok, frame = capture.read()
            if not ok:
                continue
            frames.append((frame_idx / fps, frame))

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
            verdict = "딥페이크 가능성이 높습니다"
        elif ai_percent >= 40:
            verdict = "일부 구간에서 이상 신호가 감지되었습니다"
        else:
            verdict = "실제 촬영 영상일 가능성이 높습니다"

        # 판정 방식을 요약문에도 정확히 적는다. details.method만 맞고 문구가
        # 어긋나면, 요약만 읽는 사용자는 여전히 잘못된 정보를 받는다.
        if method == METHOD_MODEL:
            basis = f"프레임 {sampled_frames}개를 딥페이크 판별 모델({model_name})로 분석"
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
