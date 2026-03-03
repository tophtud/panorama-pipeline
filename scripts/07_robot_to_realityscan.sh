#!/bin/bash
# =============================================================================
# 07_robot_to_realityscan.sh
# 로봇.mp4 → 파노라마 이미지 추출 → RealityScan 3D 메쉬 생성 → 웹 뷰어 통합
#
# 사용법:
#   cd ~/뉴딕스\ 작업파일/panorama-pipeline
#   bash scripts/07_robot_to_realityscan.sh
#
# 전제조건:
#   - RealityScan 2.1 설치됨 (sudo apt install ~/Downloads/RealityScan-2.1.deb)
#   - ffmpeg 설치됨 (sudo apt install ffmpeg)
#   - 로봇.mp4 파일이 panorama-pipeline 폴더에 있음
# =============================================================================

set -e

# ─── 경로 설정 ───────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VIDEO_FILE=""
IMAGES_DIR="$BASE_DIR/output/images"
MESH_DIR="$BASE_DIR/output/mesh"
PROJECT_FILE="$BASE_DIR/output/realityscan_project.rsproj"

# 영상 파일 자동 탐색 (로봇.mp4 또는 로봇 .mp4)
for f in "$BASE_DIR/로봇.mp4" "$BASE_DIR/로봇 .mp4" "$BASE_DIR"/*.mp4; do
    if [ -f "$f" ]; then
        VIDEO_FILE="$f"
        break
    fi
done

# 색상 출력
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

echo ""
echo "======================================================"
echo "  로봇.mp4 → RealityScan 3D 메쉬 파이프라인"
echo "======================================================"
echo ""

# ─── 사전 확인 ───────────────────────────────────────────────────────────────
if [ -z "$VIDEO_FILE" ]; then
    error "영상 파일을 찾을 수 없습니다.\n  panorama-pipeline 폴더에 '로봇.mp4' 파일이 있는지 확인하세요."
fi
info "영상 파일: $VIDEO_FILE"

# ffmpeg 확인
if ! command -v ffmpeg &>/dev/null; then
    warn "ffmpeg이 없습니다. 설치 중..."
    sudo apt-get install -y ffmpeg
fi

# RealityScan 실행 파일 탐색
find_rs() {
    for candidate in \
        "RealityScan" \
        "/opt/RealityScan/RealityScan" \
        "/usr/bin/RealityScan" \
        "/usr/local/bin/RealityScan"; do
        if command -v "$candidate" &>/dev/null 2>&1 || [ -f "$candidate" ]; then
            echo "$candidate"; return
        fi
    done
    # Wine 번들 탐색
    local exe
    exe=$(find /opt -name "RealityScan.exe" -type f 2>/dev/null | head -1)
    if [ -n "$exe" ]; then
        local wine_bin
        wine_bin=$(find /opt -name "wine" -type f 2>/dev/null | head -1)
        if [ -n "$wine_bin" ]; then
            echo "$wine_bin $exe"; return
        elif command -v wine &>/dev/null; then
            echo "wine $exe"; return
        fi
    fi
    echo ""
}

RS=$(find_rs)
if [ -z "$RS" ]; then
    error "RealityScan을 찾을 수 없습니다.\n  먼저 설치하세요: sudo apt install ~/Downloads/RealityScan-2.1.deb"
fi
info "RealityScan: $RS"

# ─── 1단계: 영상 정보 확인 ───────────────────────────────────────────────────
info "영상 정보 확인 중..."
DURATION=$(ffprobe -v quiet -show_entries format=duration \
    -of default=noprint_wrappers=1:nokey=1 "$VIDEO_FILE" 2>/dev/null | cut -d. -f1)
FPS=$(ffprobe -v quiet -select_streams v:0 \
    -show_entries stream=r_frame_rate \
    -of default=noprint_wrappers=1:nokey=1 "$VIDEO_FILE" 2>/dev/null | head -1)
info "  길이: ${DURATION}초, 프레임레이트: $FPS"

# ─── 2단계: 파노라마 이미지 추출 ─────────────────────────────────────────────
# Insta360 X3: 3840x1920 equirectangular
# RealityScan에 최적화: 1초에 1장 (과도한 중복 방지), 최대 300장
info "파노라마 이미지 추출 중..."
mkdir -p "$IMAGES_DIR"

# 기존 이미지 확인
EXISTING=$(find "$IMAGES_DIR" -name "frame_*.jpg" 2>/dev/null | wc -l)
if [ "$EXISTING" -gt 10 ]; then
    warn "이미 ${EXISTING}개 이미지가 있습니다. 건너뜁니다. (재추출하려면 output/images 폴더를 비우세요)"
else
    # 1초에 2장 추출 (총 영상 길이에 따라 자동 조정)
    # Insta360 X3 원본 해상도 유지 (3840x1920)
    ffmpeg -i "$VIDEO_FILE" \
        -vf "fps=2,scale=3840:1920" \
        -q:v 2 \
        -frames:v 300 \
        "$IMAGES_DIR/frame_%04d.jpg" \
        -y 2>/dev/null

    IMG_COUNT=$(find "$IMAGES_DIR" -name "frame_*.jpg" | wc -l)
    info "이미지 추출 완료: ${IMG_COUNT}장 → $IMAGES_DIR"

    if [ "$IMG_COUNT" -lt 10 ]; then
        error "이미지가 너무 적습니다 (${IMG_COUNT}장). 영상 파일을 확인하세요."
    fi
fi

# ─── 3단계: RealityScan 3D 메쉬 생성 ────────────────────────────────────────
info "RealityScan 3D 재구성 시작..."
info "  (이미지 수에 따라 20분~1시간 소요됩니다)"
mkdir -p "$MESH_DIR"

MESH_OUT="$MESH_DIR/scene_mesh.glb"

$RS \
    -headless \
    -newScene \
    -addFolder "$IMAGES_DIR" \
    -align \
    -selectMaximalComponent \
    -calculateNormalModel \
    -selectMaximalComponent \
    -unwrap \
    -calculateTexture \
    -exportSelectedModel "$MESH_OUT" \
    -save "$PROJECT_FILE" \
    -quit

# ─── 4단계: 결과 확인 및 웹 뷰어 통합 ───────────────────────────────────────
if [ -f "$MESH_OUT" ]; then
    SIZE=$(du -sh "$MESH_OUT" | cut -f1)
    info "3D 메쉬 생성 완료: $MESH_OUT ($SIZE)"
else
    # GLB 실패 시 OBJ로 재시도
    warn "GLB 생성 실패. OBJ 포맷으로 재시도..."
    MESH_OUT="$MESH_DIR/scene_mesh.obj"
    $RS \
        -headless \
        -load "$PROJECT_FILE" \
        -selectMaximalComponent \
        -exportSelectedModel "$MESH_OUT" \
        -quit
fi

if [ -f "$MESH_OUT" ]; then
    SIZE=$(du -sh "$MESH_OUT" | cut -f1)
    info "메쉬 저장 완료: $MESH_OUT ($SIZE)"
else
    error "메쉬 생성에 실패했습니다. RealityScan 로그를 확인하세요."
fi

# ─── 5단계: 완료 안내 ────────────────────────────────────────────────────────
echo ""
echo "======================================================"
echo -e "${GREEN}  완료! 웹 뷰어 실행 방법:${NC}"
echo "======================================================"
echo ""
echo "  bash start_viewer.sh 8080"
echo "  → 브라우저에서 http://localhost:8080/web/ 접속"
echo "  → 🗺 3D 맵 버튼 클릭하면 RealityScan 메쉬 표시"
echo ""
