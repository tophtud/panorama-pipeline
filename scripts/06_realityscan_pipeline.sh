#!/bin/bash
# =============================================================================
# 06_realityscan_pipeline.sh
# RealityScan 2.1 설치 + 파노라마 이미지 → 3D 메쉬 → 웹 뷰어 통합 자동화
#
# 사용법:
#   bash scripts/06_realityscan_pipeline.sh [옵션]
#
# 옵션:
#   --install    RealityScan 2.1 .deb 설치만 수행
#   --mesh       3D 메쉬 생성만 수행 (이미 설치된 경우)
#   --all        설치 + 메쉬 생성 + 웹 뷰어 통합 전체 수행 (기본값)
#   --images DIR 파노라마 이미지 폴더 지정 (기본: output/images)
#   --output DIR 메쉬 출력 폴더 지정 (기본: output/mesh)
#   --quality N  메쉬 품질: 1=preview, 2=normal, 3=high (기본: 2)
# =============================================================================

set -e

# ─── 기본값 설정 ─────────────────────────────────────────────────────────────
DEB_PATH="$HOME/Downloads/RealityScan-2.1.deb"
IMAGES_DIR="$(pwd)/output/images"
MESH_DIR="$(pwd)/output/mesh"
PROJECT_FILE="$(pwd)/output/realityscan_project.rsproj"
MESH_QUALITY=2   # 1=preview, 2=normal, 3=high
MODE="all"

# RealityScan 설치 경로 (deb 설치 후 기본 위치)
RS_EXEC="/opt/RealityScan/RealityScan"
RS_EXEC_ALT="/usr/bin/RealityScan"
RS_EXEC_WINE="/opt/RealityScan/wine/bin/wine /opt/RealityScan/RealityScan.exe"

# ─── 인자 파싱 ───────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case $1 in
        --install) MODE="install"; shift ;;
        --mesh)    MODE="mesh";    shift ;;
        --all)     MODE="all";     shift ;;
        --images)  IMAGES_DIR="$2"; shift 2 ;;
        --output)  MESH_DIR="$2";   shift 2 ;;
        --quality) MESH_QUALITY="$2"; shift 2 ;;
        --deb)     DEB_PATH="$2";   shift 2 ;;
        *) echo "[ERROR] 알 수 없는 옵션: $1"; exit 1 ;;
    esac
done

# ─── 색상 출력 함수 ──────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()    { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
error()   { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# ─── RealityScan 실행 파일 찾기 ──────────────────────────────────────────────
find_realityscan() {
    # 일반 Linux 바이너리
    if command -v RealityScan &>/dev/null; then
        echo "RealityScan"; return
    fi
    if [ -f "$RS_EXEC" ]; then
        echo "$RS_EXEC"; return
    fi
    if [ -f "$RS_EXEC_ALT" ]; then
        echo "$RS_EXEC_ALT"; return
    fi
    # Wine 기반 (RealityScan 2.1 Linux는 Wine 번들)
    if [ -f "/opt/RealityScan/RealityScan.exe" ]; then
        # Wine 번들 확인
        WINE_BIN=$(find /opt/RealityScan -name "wine" -type f 2>/dev/null | head -1)
        if [ -n "$WINE_BIN" ]; then
            echo "$WINE_BIN /opt/RealityScan/RealityScan.exe"; return
        fi
        # 시스템 wine 사용
        if command -v wine &>/dev/null; then
            echo "wine /opt/RealityScan/RealityScan.exe"; return
        fi
    fi
    echo ""
}

# ─── 1단계: 설치 ─────────────────────────────────────────────────────────────
install_realityscan() {
    info "RealityScan 2.1 설치 시작..."

    if [ ! -f "$DEB_PATH" ]; then
        error ".deb 파일을 찾을 수 없습니다: $DEB_PATH\n  --deb 옵션으로 경로를 지정하세요."
    fi

    info "의존성 설치 중..."
    sudo apt-get update -qq
    sudo apt-get install -y -qq \
        libglib2.0-0 \
        libgl1-mesa-glx \
        libglu1-mesa \
        libxrender1 \
        libxrandr2 \
        libxinerama1 \
        libxi6 \
        libxcursor1 \
        libxss1 \
        libxtst6 \
        libnss3 \
        libasound2 \
        libdbus-1-3 \
        libatk1.0-0 \
        libgtk-3-0 \
        wine64 \
        wine32 2>/dev/null || true

    info "RealityScan .deb 설치 중: $DEB_PATH"
    sudo dpkg -i "$DEB_PATH" || sudo apt-get install -f -y

    # 설치 확인
    RS=$(find_realityscan)
    if [ -z "$RS" ]; then
        warn "RealityScan 실행 파일을 찾지 못했습니다."
        warn "설치 경로를 확인하세요:"
        find /opt /usr -name "RealityScan*" -type f 2>/dev/null | head -10
    else
        info "설치 완료: $RS"
    fi
}

# ─── 2단계: 3D 메쉬 생성 ─────────────────────────────────────────────────────
generate_mesh() {
    RS=$(find_realityscan)
    if [ -z "$RS" ]; then
        error "RealityScan을 찾을 수 없습니다. 먼저 --install 을 실행하세요."
    fi

    if [ ! -d "$IMAGES_DIR" ]; then
        error "이미지 폴더를 찾을 수 없습니다: $IMAGES_DIR"
    fi

    IMG_COUNT=$(find "$IMAGES_DIR" -name "*.jpg" -o -name "*.png" -o -name "*.JPG" | wc -l)
    if [ "$IMG_COUNT" -lt 3 ]; then
        error "이미지가 너무 적습니다 ($IMG_COUNT개). 최소 3장 이상 필요합니다."
    fi

    info "이미지 ${IMG_COUNT}개 발견: $IMAGES_DIR"
    mkdir -p "$MESH_DIR"

    # 품질 명령어 선택
    case $MESH_QUALITY in
        1) QUALITY_CMD="-calculatePreviewModel" ;;
        3) QUALITY_CMD="-calculateHighModel" ;;
        *) QUALITY_CMD="-calculateNormalModel" ;;
    esac

    # 출력 파일 경로
    MESH_OUT="$MESH_DIR/scene_mesh.glb"

    info "RealityScan CLI 실행 중..."
    info "  이미지 폴더: $IMAGES_DIR"
    info "  출력 메쉬:   $MESH_OUT"
    info "  품질:        $MESH_QUALITY (1=preview, 2=normal, 3=high)"

    # RealityScan CLI 실행
    $RS \
        -headless \
        -newScene \
        -addFolder "$IMAGES_DIR" \
        -align \
        -selectMaximalComponent \
        $QUALITY_CMD \
        -selectMaximalComponent \
        -unwrap \
        -calculateTexture \
        -exportSelectedModel "$MESH_OUT" \
        -save "$PROJECT_FILE" \
        -quit

    if [ -f "$MESH_OUT" ]; then
        SIZE=$(du -sh "$MESH_OUT" | cut -f1)
        info "메쉬 생성 완료: $MESH_OUT ($SIZE)"
    else
        # OBJ 포맷으로 재시도
        warn "GLB 내보내기 실패. OBJ 포맷으로 재시도..."
        MESH_OUT_OBJ="$MESH_DIR/scene_mesh.obj"
        $RS \
            -headless \
            -load "$PROJECT_FILE" \
            -selectMaximalComponent \
            -exportSelectedModel "$MESH_OUT_OBJ" \
            -quit
        if [ -f "$MESH_OUT_OBJ" ]; then
            info "OBJ 메쉬 생성 완료: $MESH_OUT_OBJ"
        else
            error "메쉬 생성에 실패했습니다."
        fi
    fi
}

# ─── 3단계: 웹 뷰어 통합 ─────────────────────────────────────────────────────
integrate_to_viewer() {
    info "웹 뷰어 통합 중..."

    # Python 스크립트로 통합
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    if [ -f "$SCRIPT_DIR/05_realityscan_to_web.py" ]; then
        # GLB 우선, 없으면 OBJ
        if [ -f "$MESH_DIR/scene_mesh.glb" ]; then
            python3 "$SCRIPT_DIR/05_realityscan_to_web.py" \
                --input "$MESH_DIR/scene_mesh.glb" \
                --output_dir "$MESH_DIR"
        elif [ -f "$MESH_DIR/scene_mesh.obj" ]; then
            python3 "$SCRIPT_DIR/05_realityscan_to_web.py" \
                --input "$MESH_DIR/scene_mesh.obj" \
                --output_dir "$MESH_DIR"
        fi
    fi

    info "완료! 웹 뷰어를 실행하려면:"
    echo ""
    echo "  bash start_viewer.sh 8080"
    echo "  → http://localhost:8080/web/ 접속"
    echo "  → 🗺 3D 맵 버튼 클릭"
    echo ""
}

# ─── 메인 실행 ───────────────────────────────────────────────────────────────
echo ""
echo "======================================================"
echo "  RealityScan 2.1 파노라마 3D 메쉬 파이프라인"
echo "======================================================"
echo ""

case $MODE in
    install)
        install_realityscan
        ;;
    mesh)
        generate_mesh
        integrate_to_viewer
        ;;
    all)
        install_realityscan
        generate_mesh
        integrate_to_viewer
        ;;
esac

info "파이프라인 완료!"
