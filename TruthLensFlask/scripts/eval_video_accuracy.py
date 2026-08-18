"""영상 판별 정확도를 라벨된 영상 세트로 측정한다.

이미지는 35장으로 재서 94.3%라는 숫자가 있는데 영상은 그런 게 없었다.
"정확도가 이게 최선인가"에 답하려면 먼저 재야 한다.

사용법:
    python scripts/eval_video_accuracy.py --ai <AI생성영상폴더> --real <실촬영영상폴더>

세 방식을 같은 프레임에 나란히 돌린다. 프레임 샘플링은 한 번만 하므로
방식 간 비교가 공정하다.

    ensemble   지금 쓰는 방식. AI 생성 탐지 3모델 중앙값 → 프레임 중앙값
    deepfake   교체 전 방식. 얼굴 조작 탐지기 평균 * 0.8 + 시간적 일관성 * 0.2
    heuristic  토큰이 없을 때의 폴백. 로컬 픽셀 휴리스틱 중앙값

결과는 output/video_eval/ 에 저장한다.
"""
import argparse
import csv
import os
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from ai_models.hf_deepfake_client import (  # noqa: E402
    IMAGE_ENSEMBLE_MODELS,
    HFDeepfakeClient,
    HFInferenceError,
    collect_model_scores,
)
from ai_models.pixel_heuristics import analyze_pixel_patterns  # noqa: E402
from ai_models.video_detector import VideoDetector  # noqa: E402

# 교체 전에 영상이 쓰던 모델. 비교 대상으로만 남긴다.
OLD_DEEPFAKE_MODEL = "prithivMLmods/deepfake-detector-model-v1"
VIDEO_SUFFIXES = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
DECISION_THRESHOLD = 60


def _video_files(directory):
    return sorted(
        p for p in Path(directory).iterdir()
        if p.is_file() and p.suffix.lower() in VIDEO_SUFFIXES
    )


def _score_one(path, token, detector):
    """한 영상에서 프레임을 한 번만 뽑아 세 방식으로 각각 채점한다."""
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        capture.release()
        return None
    frames = detector._sample_frames(capture)
    capture.release()
    if not frames:
        return None

    blobs = [cv2.imencode('.jpg', frame)[1].tobytes() for _, frame in frames]

    heuristic = [
        analyze_pixel_patterns(
            cv2.cvtColor(cv2.resize(frame, (224, 224)), cv2.COLOR_BGR2RGB)
        )["ai_percent"]
        for _, frame in frames
    ]
    temporal = detector._analyze_temporal_consistency(frames)

    scores = {"heuristic": round(statistics.median(heuristic), 1)}

    if token:
        per_frame = []
        for blob in blobs:
            got = collect_model_scores(token, IMAGE_ENSEMBLE_MODELS, blob, timeout=20)
            if got:
                per_frame.append(statistics.median(got.values()))
        scores["ensemble"] = round(statistics.median(per_frame), 1) if per_frame else None

        old = []
        for blob in blobs:
            try:
                old.append(HFDeepfakeClient(token, OLD_DEEPFAKE_MODEL).fake_percent(blob))
            except HFInferenceError:
                pass
        scores["deepfake"] = (
            round(float(np.mean(old)) * 0.8 + temporal["temporal_ai_score"] * 0.2, 1)
            if old else None
        )
    else:
        scores["ensemble"] = None
        scores["deepfake"] = None

    return scores


def _confusion(rows, method, threshold):
    """AI를 AI로 / 진본을 진본으로 맞춘 개수를 센다."""
    tp = fn = tn = fp = skipped = 0
    for row in rows:
        score = row["scores"].get(method)
        if score is None:
            skipped += 1
            continue
        flagged = score >= threshold
        if row["label"] == "ai":
            tp += flagged
            fn += not flagged
        else:
            fp += flagged
            tn += not flagged
    total = tp + fn + tn + fp
    accuracy = round((tp + tn) / total * 100, 1) if total else 0.0
    return {"tp": tp, "fn": fn, "tn": tn, "fp": fp,
            "accuracy": accuracy, "skipped": skipped, "total": total}


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ai", required=True, help="AI로 생성한 영상이 든 폴더")
    parser.add_argument("--real", required=True, help="실제 촬영한 영상이 든 폴더")
    parser.add_argument("--out", default=str(ROOT.parent / "output" / "video_eval"))
    args = parser.parse_args()

    token = (os.getenv("HF_TOKEN") or "").strip()
    if not token:
        print("HF_TOKEN이 없어 로컬 휴리스틱만 측정합니다.", file=sys.stderr)

    detector = VideoDetector()
    rows = []
    for label, directory in (("ai", args.ai), ("real", args.real)):
        files = _video_files(directory)
        if not files:
            print(f"{directory}에 영상이 없습니다.", file=sys.stderr)
        for path in files:
            scores = _score_one(path, token, detector)
            if scores is None:
                print(f"  건너뜀(열 수 없음): {path.name}", file=sys.stderr)
                continue
            rows.append({"file": path.name, "label": label, "scores": scores})
            cells = "  ".join(
                f"{m}={scores.get(m) if scores.get(m) is not None else '-':>6}"
                for m in ("ensemble", "deepfake", "heuristic")
            )
            print(f"[{label:4}] {path.name[:40]:42} {cells}")

    if not rows:
        print("측정할 영상이 없습니다.", file=sys.stderr)
        return 1

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    with (out_dir / "scores.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["file", "label", "ensemble", "deepfake", "heuristic"])
        for row in rows:
            writer.writerow([row["file"], row["label"],
                             row["scores"].get("ensemble"),
                             row["scores"].get("deepfake"),
                             row["scores"].get("heuristic")])

    methods = ("ensemble", "deepfake", "heuristic")
    lines = ["# 영상 판별 정확도 측정", ""]
    lines.append(f"AI 생성 {sum(r['label'] == 'ai' for r in rows)}개, "
                 f"실촬영 {sum(r['label'] == 'real' for r in rows)}개")
    lines += ["", f"## 판정 기준 {DECISION_THRESHOLD}%", "",
              "| 방식 | 정확도 | AI를 AI로 | AI를 놓침 | 진본을 진본으로 | 진본을 의심(오탐) | 측정 실패 |",
              "|---|---|---|---|---|---|---|"]
    for method in methods:
        c = _confusion(rows, method, DECISION_THRESHOLD)
        lines.append(f"| {method} | {c['accuracy']}% | {c['tp']} | {c['fn']} | "
                     f"{c['tn']} | {c['fp']} | {c['skipped']} |")

    lines += ["", "## 판정 기준을 바꾸면", "",
              "| 기준 | " + " | ".join(methods) + " |",
              "|---|" + "---|" * len(methods)]
    for threshold in range(20, 90, 10):
        cells = " | ".join(f"{_confusion(rows, m, threshold)['accuracy']}%" for m in methods)
        lines.append(f"| {threshold}% | {cells} |")

    lines += ["", "## 영상별 점수", "",
              "| 파일 | 정답 | " + " | ".join(methods) + " |",
              "|---|---|" + "---|" * len(methods)]
    for row in rows:
        cells = " | ".join(
            str(row["scores"].get(m)) if row["scores"].get(m) is not None else "-"
            for m in methods
        )
        lines.append(f"| {row['file']} | {row['label']} | {cells} |")

    report = out_dir / "report.md"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n리포트: {report}")
    print(f"원자료: {out_dir / 'scores.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
