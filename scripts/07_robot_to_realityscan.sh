#!/bin/bash
# =============================================================================
# 07_robot_to_realityscan.sh
# 로봇.mp4 → 파노라마 이미지 추출 → RealityScan 3D 메쉬 생성 → 웹 뷰어 통합
#
# 사용법:
#   cd ~/뉴딕스\ 작업파일/panorama-pipeline
#   bash scripts/07_robot_to_realityscan.sh
# =============================================================================

set -e

# ─── 경로 설정 ───────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VIDEO_FILE=""
IMAGES_DIR="$BASE_DIR/output/images"
MESH_DIR="$BASE_DIR/output/mesh"
PROJECT_FILE="$BASE_DIR/output/realityscan_project.rsproj"

# 영상 파일 자동 탐색
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
    # 1) 시스템 PATH에 있는 경우
    if command -v RealityScan &>/dev/null; then
        echo "RealityScan"; return
    fi
    # 2) Wine 번들 탐색
    for wine_dir in /opt/realityscan /opt/RealityScan /usr/lib/realityscan; do
        local exe
        exe=$(find "$wine_dir" -name "RealityScan.exe" -type f 2>/dev/null | head -1)
        if [ -n "$exe" ]; then
            local wine_bin
            wine_bin=$(find "$wine_dir" -name "wine" -type f 2>/dev/null | head -1)
            if [ -n "$wine_bin" ]; then
                echo "$wine_bin $exe"; return
            elif command -v wine &>/dev/null; then
                echo "wine $exe"; return
            fi
        fi
    done
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
info "  길이: ${DURATION}초"

# ─── 2단계: 파노라마 이미지 추출 ─────────────────────────────────────────────
info "파노라마 이미지 추출 중..."
mkdir -p "$IMAGES_DIR"

EXISTING=$(find "$IMAGES_DIR" -name "frame_*.jpg" 2>/dev/null | wc -l)
if [ "$EXISTING" -gt 10 ]; then
    warn "이미 ${EXISTING}개 이미지가 있습니다. 건너뜁니다. (재추출하려면 output/images 폴더를 비우세요)"
else
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

# ─── 3단계: .rscmd 배치 파일 생성 ────────────────────────────────────────────
# 주의: importColmap CLI는 현재 RealityScan 2.1에서 버그로 작동 안 함
# (https://forums.unrealengine.com/t/cli-for-importing-colmap-text-format/2613942)
# 대신 이미지 폴더에서 직접 정렬 수행
mkdir -p "$MESH_DIR"

RSCMD_FILE="$BASE_DIR/output/run_reconstruction.rscmd"
# 출력 파일명 (공백 없는 경로 사용)
MESH_OUT_OBJ="$MESH_DIR/scene_mesh.obj"
MESH_OUT_GLB="$MESH_DIR/scene_mesh.glb"

# .rscmd 파일 생성
# exportSelectedModel의 fileName은 경로+파일명+확장자 (params.xml 없이)
cat > "$RSCMD_FILE" << RSCMD_EOF
-headless
-newScene
-addFolder "$IMAGES_DIR"
-align
-selectMaximalComponent
-calculateNormalModel
-selectMaximalComponent
-unwrap
-calculateTexture
-exportSelectedModel "$MESH_OUT_OBJ"
-save "$PROJECT_FILE"
-quit
RSCMD_EOF

info "배치 파일 생성: $RSCMD_FILE"

# ─── 4단계: RealityScan 실행 ─────────────────────────────────────────────────
info "RealityScan 3D 재구성 시작..."
info "  (이미지 수에 따라 20분~1시간 소요됩니다)"
info "  GStreamer 경고 메시지는 무시해도 됩니다"

export DISPLAY="${DISPLAY:-:0}"

# execRSCMD로 배치 파일 실행 (경로 공백 문제 우회)
$RS -execRSCMD "$RSCMD_FILE" 2>&1 | \
    grep -v "GStreamer-CRITICAL\|GStreamer-Video-CRITICAL\|gst_query_set_uri\|gst_video_info_from_caps" || true

# ─── 5단계: 결과 확인 ────────────────────────────────────────────────────────
RESULT_FILE=""
for f in "$MESH_OUT_OBJ" "$MESH_OUT_GLB"; do
    if [ -f "$f" ]; then
        RESULT_FILE="$f"
        break
    fi
done

if [ -n "$RESULT_FILE" ]; then
    SIZE=$(du -sh "$RESULT_FILE" | cut -f1)
    info "메쉬 생성 완료: $RESULT_FILE ($SIZE)"
else
    warn ""
    warn "메쉬 파일이 생성되지 않았습니다."
    warn "RealityScan GUI를 직접 사용하는 방법 (권장):"
    echo ""
    echo "  ┌─────────────────────────────────────────────────────────┐"
    echo "  │  1. RealityScan GUI 실행                                 │"
    echo "  │  2. [1] Inputs → Images 클릭                            │"
    echo "  │     이미지 폴더: $IMAGES_DIR"
    echo "  │  3. [2] Process → Align Images 클릭 (수 분 대기)        │"
    echo "  │  4. Calculate Model → Normal 클릭 (20~40분 대기)        │"
    echo "  │  5. Texture & Colorize 클릭                             │"
    echo "  │  6. [3] Output → Export 클릭                            │"
    echo "  │     포맷: OBJ 또는 GLB                                  │"
    echo "  │     저장 경로: $MESH_DIR/scene_mesh.glb"
    echo "  └─────────────────────────────────────────────────────────┘"
    echo ""
    exit 1
fi

# ─── 6단계: 완료 안내 ────────────────────────────────────────────────────────
echo ""
echo "======================================================"
echo -e "${GREEN}  완료! 웹 뷰어 실행 방법:${NC}"
echo "======================================================"
echo ""
echo "  bash start_viewer.sh 8080"
echo "  → 브라우저에서 http://localhost:8080/web/ 접속"
echo "  → 🗺 3D 맵 버튼 클릭하면 RealityScan 메쉬 표시"
echo ""
