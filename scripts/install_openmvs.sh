#!/bin/bash
# ============================================================
# OpenMVS 자동 빌드 스크립트 (Ubuntu 20.04 / 22.04)
# stella_vSLAM 파노라마 파이프라인용
# 실행: bash scripts/install_openmvs.sh
# ============================================================
set -e

INSTALL_DIR="$HOME/openmvs_build"
LOCAL_BIN="$HOME/.local/bin"
JOBS=$(nproc)

echo "============================================================"
echo "  OpenMVS 자동 빌드 시작 (CPU: $JOBS 코어)"
echo "============================================================"

# ── 1. 시스템 의존성 설치 ──────────────────────────────────────
echo "[1/6] 시스템 패키지 설치..."
sudo apt-get update -qq
sudo apt-get install -y \
  build-essential cmake git wget \
  libboost-iostreams-dev libboost-program-options-dev \
  libboost-system-dev libboost-serialization-dev \
  libopencv-dev libcgal-dev \
  libatlas-base-dev libsuitesparse-dev \
  freeglut3-dev libglew-dev \
  libpng-dev libjpeg-dev libtiff-dev \
  python3-dev 2>/dev/null

sudo apt-get install -y libvtk9-dev 2>/dev/null || \
sudo apt-get install -y libvtk7-dev 2>/dev/null || \
echo "  [WARN] VTK 없음 (선택 사항)"

# ── 2. Eigen 3.4 확인 및 설치 ─────────────────────────────────
echo "[2/6] Eigen 버전 확인..."
EIGEN_VER=$(pkg-config --modversion eigen3 2>/dev/null || echo "0.0.0")
EIGEN_MAJOR=$(echo $EIGEN_VER | cut -d. -f1)
EIGEN_MINOR=$(echo $EIGEN_VER | cut -d. -f2)

if [ "$EIGEN_MAJOR" -lt 3 ] || ([ "$EIGEN_MAJOR" -eq 3 ] && [ "$EIGEN_MINOR" -lt 4 ]); then
  echo "  Eigen $EIGEN_VER 감지 → 3.4.0 소스 빌드..."
  mkdir -p "$INSTALL_DIR/eigen"
  cd "$INSTALL_DIR/eigen"
  if [ ! -f "eigen-3.4.0.tar.gz" ]; then
    wget -q https://gitlab.com/libeigen/eigen/-/archive/3.4.0/eigen-3.4.0.tar.gz
  fi
  tar xzf eigen-3.4.0.tar.gz 2>/dev/null || true
  mkdir -p eigen-3.4.0/build && cd eigen-3.4.0/build
  cmake .. -DCMAKE_INSTALL_PREFIX=/usr/local -DCMAKE_BUILD_TYPE=Release > /dev/null
  sudo make install -j$JOBS > /dev/null
  echo "  Eigen 3.4.0 설치 완료"
  EIGEN_INCLUDE="/usr/local/include/eigen3"
else
  echo "  Eigen $EIGEN_VER (OK)"
  EIGEN_INCLUDE=$(pkg-config --variable=includedir eigen3)/eigen3
fi

# ── 3. VCGLib 클론 ─────────────────────────────────────────────
echo "[3/6] VCGLib 다운로드..."
mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"
if [ ! -d "vcglib" ]; then
  git clone --depth=1 https://github.com/cdcseacave/VCG.git vcglib
  echo "  VCGLib 클론 완료"
else
  echo "  VCGLib 이미 존재 (스킵)"
fi

# ── 4. OpenMVS 클론 ────────────────────────────────────────────
echo "[4/6] OpenMVS 소스 다운로드..."
cd "$INSTALL_DIR"
if [ ! -d "openMVS" ]; then
  git clone --depth=1 https://github.com/cdcseacave/openMVS.git
  echo "  OpenMVS 클론 완료"
else
  echo "  OpenMVS 이미 존재 (스킵)"
fi

# ── 5. OpenMVS 빌드 ────────────────────────────────────────────
echo "[5/6] OpenMVS 빌드 중... (약 10~20분 소요)"
mkdir -p "$INSTALL_DIR/openMVS/build"
cd "$INSTALL_DIR/openMVS/build"

cmake .. \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX="$HOME/.local" \
  -DVCG_ROOT="$INSTALL_DIR/vcglib" \
  -DEIGEN3_INCLUDE_DIR="$EIGEN_INCLUDE" \
  -DOpenMVS_USE_CUDA=OFF \
  -DBUILD_SHARED_LIBS=OFF \
  2>&1 | tail -3

make -j$JOBS 2>&1 | grep -E "^\[|error:" | tail -30
make install

# ── 6. PATH 등록 ───────────────────────────────────────────────
echo "[6/6] PATH 등록..."
mkdir -p "$LOCAL_BIN"

# 빌드 디렉토리에서 바이너리 심볼릭 링크 생성 (make install 실패 대비)
for cmd in InterfaceCOLMAP DensifyPointCloud ReconstructMesh TextureMesh; do
  BIN_PATH="$INSTALL_DIR/openMVS/build/bin/$cmd"
  if [ -f "$BIN_PATH" ] && [ ! -f "$LOCAL_BIN/$cmd" ]; then
    ln -sf "$BIN_PATH" "$LOCAL_BIN/$cmd"
    echo "  링크 생성: $LOCAL_BIN/$cmd"
  fi
done

if ! grep -q '.local/bin' ~/.bashrc; then
  echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
fi
export PATH="$LOCAL_BIN:$PATH"

echo ""
echo "============================================================"
echo "  OpenMVS 설치 완료!"
echo "============================================================"
echo ""
echo "  설치된 도구:"
for cmd in InterfaceCOLMAP DensifyPointCloud ReconstructMesh TextureMesh; do
  if command -v $cmd &>/dev/null || [ -f "$LOCAL_BIN/$cmd" ]; then
    echo "    ✅ $cmd"
  else
    echo "    ❌ $cmd"
  fi
done
echo ""
echo "  다음 단계:"
echo "    source ~/.bashrc"
echo "    cd ~/뉴딕스\ 작업파일/panorama_pipeline"
echo "    python3 scripts/04_run_openmvs.py --data_dir output"
