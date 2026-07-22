import cv2
import numpy as np


def analyze_pixel_patterns(img_array):
    """RGB 이미지 배열(H,W,3)의 픽셀 패턴으로 AI 개입 비율을 계산한다.

    이미지/영상 프레임 판별기가 공통으로 사용하는 휴리스틱.
    분석 항목 3가지를 각각 점수 내서 종합한다.

    1. 노이즈 균일도: AI 이미지는 노이즈가 지나치게 균일
    2. 엣지 패턴: AI 이미지는 경계선이 너무 매끄러움
    3. 색상 분포: AI 이미지는 색상이 과도하게 균형잡혀 있음
    """
    # --- 분석 1: 노이즈 균일도 ---
    noise_scores = []
    for ch in range(3):
        ch_data = img_array[:, :, ch].astype(float)
        lap = cv2.Laplacian(ch_data, cv2.CV_64F)
        noise_scores.append(np.var(lap))
    avg_noise = np.mean(noise_scores)

    # 노이즈 분산이 낮을수록 AI 가능성 높음
    if avg_noise < 100:
        noise_ai_score = 90
    elif avg_noise < 300:
        noise_ai_score = 70
    elif avg_noise < 600:
        noise_ai_score = 45
    elif avg_noise < 1000:
        noise_ai_score = 25
    else:
        noise_ai_score = 10

    # --- 분석 2: 엣지 매끄러움 ---
    gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    edge_density = np.sum(edges > 0) / edges.size

    # 엣지가 너무 적거나 너무 균일하면 AI 의심
    if edge_density < 0.03:
        edge_ai_score = 80
    elif edge_density < 0.08:
        edge_ai_score = 55
    elif edge_density < 0.15:
        edge_ai_score = 35
    else:
        edge_ai_score = 15

    # --- 분석 3: 색상 분포 균일도 ---
    color_stds = [np.std(img_array[:, :, ch]) for ch in range(3)]
    avg_color_std = np.mean(color_stds)

    # 색상 표준편차가 지나치게 균일하면 AI 의심
    if avg_color_std < 30:
        color_ai_score = 75
    elif avg_color_std < 50:
        color_ai_score = 50
    elif avg_color_std < 70:
        color_ai_score = 30
    else:
        color_ai_score = 15

    # --- 종합 점수 (가중 평균) ---
    # 노이즈가 가장 신뢰도 높아서 비중 높게
    ai_percent = round(
        noise_ai_score * 0.5 +
        edge_ai_score * 0.3 +
        color_ai_score * 0.2,
        1
    )

    # 신뢰도: 3개 분석이 일치할수록 높음
    scores = [noise_ai_score, edge_ai_score, color_ai_score]
    score_std = np.std(scores)
    if score_std < 10:
        confidence = 90
    elif score_std < 20:
        confidence = 75
    elif score_std < 30:
        confidence = 55
    else:
        confidence = 35

    return {
        "ai_percent": ai_percent,
        "confidence": confidence,
    }
