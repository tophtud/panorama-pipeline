#!/bin/bash
# ============================================================
# COLMAP CUDA 지원 버전 소스 빌드 스크립트
# Ubuntu 20.04/22.04 + CUDA 환경용
# 실행: bash scripts/install_colmap_cuda.sh
# ============================================================
set -e

echo "============================================================"
echo "  COLMAP CUDA 지원 버전 빌드"
echo "============================================================"

# ── CUDA 버전 확인 ────────────────────────────────────────────
echo "[0] CUDA 환경 확인..."
if command -v nvcc &>/dev/null; then
    CUDA_VER=$(nvcc --version | grep "release" | awk '{print $6}' | cut -c2-)
    echo "  CUDA: $CUDA_VER"
elif [ -f /usr/local/cuda/version.txt ]; then
    CUDA_VER=$(cat /usr/local/cuda/version.txt | awk '{print $3}')
    echo "  CUDA: $CUDA_VER"
else
    echo "  [WARN] CUDA 버전 확인 불가 - 계속 진행"
fi

nvidia-smi 2>/dev/null | head -3 || echo "  [WARN] nvidia-smi 없음"

# ── 기존 COLMAP 제거 ──────────────────────────────────────────
echo "[1] 기존 COLMAP 제거..."
sudo apt-get remove -y colmap 2>/dev/null || true

# ── 의존성 설치 ───────────────────────────────────────────────
echo "[2] 의존성 설치..."
sudo apt-get update -qq
sudo apt-get install -y \
    cmake ninja-build \
    libboost-program-options-dev libboost-filesystem-dev \
    libboost-graph-dev libboost-system-dev \
    libeigen3-dev libflann-dev libfreeimage-dev \
    libmetis-dev libgoogle-glog-dev libgflags-dev \
    libsqlite3-dev libglew-dev \
    qtbase5-dev libqt5opengl5-dev libcgal-dev \
    libceres-dev 2>&1 | tail -3

# ── COLMAP 소스 다운로드 ──────────────────────────────────────
echo "[3] COLMAP 소스 다운로드..."
cd /tmp
rm -rf colmap_build
git clone https://github.com/colmap/colmap.git colmap_build --depth 1 --branch 3.9.1 2>&1 | tail -3
cd colmap_build

# ── CUDA 아키텍처 자동 감지 ───────────────────────────────────
echo "[4] CUDA 아키텍처 감지..."
CUDA_ARCH=""
if command -v nvidia-smi &>/dev/null; then
    # GPU 모델로 아키텍처 추정
    GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)
    echo "  GPU: $GPU_NAME"
    case "$GPU_NAME" in
        *"RTX 40"*|*"RTX 4090"*|*"RTX 4080"*|*"RTX 4070"*|*"RTX 4060"*) CUDA_ARCH="89" ;;
        *"RTX 30"*|*"RTX 3090"*|*"RTX 3080"*|*"RTX 3070"*|*"RTX 3060"*|*"A100"*) CUDA_ARCH="86" ;;
        *"RTX 20"*|*"RTX 2080"*|*"RTX 2070"*|*"RTX 2060"*|*"T4"*) CUDA_ARCH="75" ;;
        *"GTX 10"*|*"GTX 1080"*|*"GTX 1070"*|*"GTX 1060"*|*"P100"*) CUDA_ARCH="61" ;;
        *"GTX 9"*|*"GTX 980"*|*"GTX 970"*|*"GTX 960"*) CUDA_ARCH="52" ;;
        *) CUDA_ARCH="75;86;89" ;;  # 범용
    esac
    echo "  CUDA 아키텍처: $CUDA_ARCH"
fi

# ── CMake 빌드 ────────────────────────────────────────────────
echo "[5] CMake 빌드 (시간이 걸립니다)..."
mkdir -p build && cd build

CMAKE_ARGS="-GNinja \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX=/usr/local \
  -DCUDA_ENABLED=ON"

if [ -n "$CUDA_ARCH" ]; then
    CMAKE_ARGS="$CMAKE_ARGS -DCMAKE_CUDA_ARCHITECTURES=$CUDA_ARCH"
else
    CMAKE_ARGS="$CMAKE_ARGS -DCMAKE_CUDA_ARCHITECTURES=native"
fi

cmake $CMAKE_ARGS .. 2>&1 | tail -10

echo "  빌드 시작 (CPU 코어: $(nproc))..."
ninja -j$(nproc) 2>&1 | tail -5

# ── 설치 ──────────────────────────────────────────────────────
echo "[6] 설치..."
sudo ninja install

# ── 검증 ──────────────────────────────────────────────────────
echo "[7] 설치 검증..."
if command -v colmap &>/dev/null; then
    echo "  ✅ COLMAP 설치 완료"
    colmap help 2>&1 | head -5
    # CUDA 지원 확인
    colmap patch_match_stereo --help 2>&1 | grep -i cuda || echo "  CUDA 지원 확인 필요"
else
    echo "  [ERROR] COLMAP 설치 실패"
    exit 1
fi

echo ""
echo "============================================================"
echo "  COLMAP CUDA 버전 설치 완료!"
echo "  이제 다시 실행하세요:"
echo "  bash scripts/05_run_colmap.sh output"
echo "============================================================"
