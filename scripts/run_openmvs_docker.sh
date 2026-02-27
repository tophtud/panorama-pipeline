#!/bin/bash
# ============================================================
# Docker를 이용한 OpenMVS 3D 재구성 실행 스크립트
# 실행: bash run_openmvs_docker.sh [data_dir] [resolution_level]
#
# 예시:
#   bash run_openmvs_docker.sh output 1
#   bash run_openmvs_docker.sh output 2   # 더 빠른 처리 (저해상도)
# ============================================================

DATA_DIR="${1:-output}"
RESOLUTION="${2:-1}"

DATA_ABS=$(realpath "$DATA_DIR")
OPENMVS_DIR="$DATA_ABS/openmvs"
COLMAP_DIR="$OPENMVS_DIR/colmap_persp"
IMAGES_DIR="$OPENMVS_DIR/images"

echo "============================================================"
echo "  OpenMVS 3D 재구성 (Docker)"
echo "  데이터 경로: $DATA_ABS"
echo "  해상도 레벨: $RESOLUTION (0=원본, 1=1/2, 2=1/4)"
echo "============================================================"

# ── Docker 설치 확인 ─────────────────────────────────────────
if ! command -v docker &>/dev/null; then
    echo "[ERROR] Docker가 설치되어 있지 않습니다."
    echo ""
    echo "  설치 방법:"
    echo "  curl -fsSL https://get.docker.com | bash"
    echo "  sudo usermod -aG docker \$USER"
    echo "  newgrp docker"
    exit 1
fi

# ── Docker 데몬 실행 확인 및 시작 ───────────────────────────
echo "[INFO] Docker 데몬 상태 확인..."
if ! docker info &>/dev/null 2>&1; then
    echo "[WARN] Docker 데몬이 실행 중이지 않습니다."
    echo "[INFO] Docker 데몬 시작 시도..."

    # systemd 방식
    if command -v systemctl &>/dev/null; then
        sudo systemctl start docker
        sleep 3
    # service 방식
    elif command -v service &>/dev/null; then
        sudo service docker start
        sleep 3
    fi

    # 재확인
    if ! docker info &>/dev/null 2>&1; then
        echo "[ERROR] Docker 데몬 시작 실패"
        echo ""
        echo "  수동으로 시작하는 방법:"
        echo "  sudo systemctl start docker    # systemd 사용 시"
        echo "  sudo service docker start      # service 사용 시"
        echo "  sudo dockerd &                 # 직접 실행"
        echo ""
        echo "  현재 사용자를 docker 그룹에 추가:"
        echo "  sudo usermod -aG docker \$USER"
        echo "  newgrp docker                  # 또는 로그아웃 후 재로그인"
        exit 1
    fi
    echo "[INFO] Docker 데몬 시작 완료"
fi

echo "[INFO] Docker 버전: $(docker --version)"

# ── 디렉토리 확인 ────────────────────────────────────────────
if [ ! -d "$COLMAP_DIR" ]; then
    echo "[ERROR] COLMAP 데이터 없음: $COLMAP_DIR"
    echo "[INFO] 먼저 실행: python3 scripts/03_to_openmvs.py --data_dir $DATA_DIR"
    exit 1
fi

IMG_COUNT=$(ls "$IMAGES_DIR"/*.jpg 2>/dev/null | wc -l)
echo "[INFO] Perspective 이미지 수: $IMG_COUNT 장"

if [ "$IMG_COUNT" -eq 0 ]; then
    echo "[ERROR] 이미지 없음: $IMAGES_DIR"
    exit 1
fi

# ── Docker 이미지 다운로드 ───────────────────────────────────
echo ""
echo "[1/5] OpenMVS Docker 이미지 다운로드..."
docker pull cdcseacave/openmvs:latest

# ── 공통 Docker 실행 옵션 ────────────────────────────────────
DOCKER_BASE="docker run --rm -v ${DATA_ABS}:/data cdcseacave/openmvs"

# ── Step 1: InterfaceCOLMAP ──────────────────────────────────
echo ""
echo "[2/5] InterfaceCOLMAP: COLMAP → .mvs 변환..."
$DOCKER_BASE InterfaceCOLMAP \
    -i /data/openmvs/colmap_persp \
    -o /data/openmvs/scene.mvs \
    --image-folder /data/openmvs/images \
    -w /data/openmvs

[ $? -ne 0 ] && echo "[ERROR] InterfaceCOLMAP 실패" && exit 1

# ── Step 2: DensifyPointCloud ────────────────────────────────
echo ""
echo "[3/5] DensifyPointCloud: 밀집 포인트 클라우드 생성..."
$DOCKER_BASE DensifyPointCloud \
    /data/openmvs/scene.mvs \
    --resolution-level "$RESOLUTION" \
    --number-views 4 \
    -w /data/openmvs

[ $? -ne 0 ] && echo "[ERROR] DensifyPointCloud 실패" && exit 1

# ── Step 3: ReconstructMesh ──────────────────────────────────
echo ""
echo "[4/5] ReconstructMesh: 3D 메시 생성..."
$DOCKER_BASE ReconstructMesh \
    /data/openmvs/scene_dense.mvs \
    -w /data/openmvs

[ $? -ne 0 ] && echo "[ERROR] ReconstructMesh 실패" && exit 1

# ── Step 4: TextureMesh ──────────────────────────────────────
echo ""
echo "[5/5] TextureMesh: 텍스처 매핑..."
$DOCKER_BASE TextureMesh \
    /data/openmvs/scene_dense_mesh.mvs \
    --export-type obj \
    -w /data/openmvs

[ $? -ne 0 ] && echo "[ERROR] TextureMesh 실패" && exit 1

# ── 결과 확인 ────────────────────────────────────────────────
echo ""
echo "============================================================"
echo "  3D 재구성 완료!"
echo "============================================================"
echo ""
echo "  생성된 파일:"
ls -lh "$OPENMVS_DIR"/*.obj 2>/dev/null | awk '{print "  ✓ " $NF " (" $5 ")"}'
ls -lh "$OPENMVS_DIR"/*.ply 2>/dev/null | awk '{print "  ✓ " $NF " (" $5 ")"}'
echo ""
echo "  3D 뷰어: meshlab $OPENMVS_DIR/scene_dense_mesh_texture.obj"
echo "  웹 뷰어: python3 scripts/05_web_viewer.py --data_dir $DATA_DIR"
