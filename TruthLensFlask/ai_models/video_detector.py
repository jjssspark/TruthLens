import logging

import cv2
import numpy as np

from ai_models.base_detector import BaseDetector
from ai_models.pixel_heuristics import analyze_pixel_patterns

logger = logging.getLogger(__name__)

MAX_SAMPLED_FRAMES = 16
FRAME_SIZE = (224, 224)
SUSPICIOUS_FRAME_THRESHOLD = 65


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

        frame_results = []
        for timestamp_sec, frame_bgr in frames:
            frame_rgb = cv2.cvtColor(cv2.resize(frame_bgr, FRAME_SIZE), cv2.COLOR_BGR2RGB)
            analysis = analyze_pixel_patterns(frame_rgb)
            frame_results.append({
                "timestamp_sec": timestamp_sec,
                "ai_percent": analysis["ai_percent"],
                "confidence": analysis["confidence"],
            })

        pixel_ai_percent = round(float(np.mean([f["ai_percent"] for f in frame_results])), 1)
        temporal = self._analyze_temporal_consistency(frames)

        # 프레임 평균 픽셀 휴리스틱 70% + 시간적 일관성 이상 신호 30%
        ai_percent = round(pixel_ai_percent * 0.7 + temporal["temporal_ai_score"] * 0.3, 1)
        confidence = round(float(np.mean([f["confidence"] for f in frame_results])), 1)

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
                "summary": self._make_summary(ai_percent, confidence, is_deepfake, len(frame_results)),
            },
        }

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

    def _make_summary(self, ai_percent, confidence, is_deepfake, sampled_frames):
        if is_deepfake:
            verdict = "딥페이크 가능성이 높습니다"
        elif ai_percent >= 40:
            verdict = "일부 구간에서 이상 신호가 감지되었습니다"
        else:
            verdict = "실제 촬영 영상일 가능성이 높습니다"

        return (
            f"{verdict} | AI 개입 {ai_percent}% | 신뢰도 {confidence}% | "
            f"샘플링된 프레임 {sampled_frames}개 기준 로컬 휴리스틱 분석 (외부 API 미사용)"
        )

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
