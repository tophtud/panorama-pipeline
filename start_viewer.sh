#!/bin/bash
# ============================================================
# 360° 파노라마 웹 뷰어 실행 스크립트
# 실행: bash start_viewer.sh [포트번호]
# 예시: bash start_viewer.sh 8080
# ============================================================

PORT="${1:-8080}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="$SCRIPT_DIR/output"

echo "============================================================"
echo "  360° 파노라마 웹 뷰어"
echo "============================================================"

# 이미지 확인
IMG_COUNT=$(ls "$OUTPUT_DIR/images/"*.jpg 2>/dev/null | wc -l)
if [ "$IMG_COUNT" -eq 0 ]; then
    echo "[ERROR] 파노라마 이미지가 없습니다: $OUTPUT_DIR/images/"
    echo "[INFO] 먼저 실행: python3 scripts/02_extract_frames.py --video <영상파일> --keyframes output/keyframes.json --output_dir output/images --mode timestamp"
    exit 1
fi

echo "  파노라마 이미지: $IMG_COUNT 장"
echo "  데이터 경로:     $OUTPUT_DIR"
echo ""

# 기존 포트 사용 중인 프로세스 종료
lsof -ti:$PORT | xargs kill -9 2>/dev/null || true

# output/ 디렉토리에서 웹 서버 실행
cd "$OUTPUT_DIR"
echo "  서버 시작: http://localhost:$PORT/web/"
echo "  종료: Ctrl+C"
echo "============================================================"
echo ""

python3 -m http.server $PORT
