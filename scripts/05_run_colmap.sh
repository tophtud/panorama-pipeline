#!/bin/bash
# ============================================================
# COLMAP 3D Dense Reconstruction (CUDA 지원 버전)
# stella_vSLAM → COLMAP → Dense Mesh 파이프라인
# 실행: bash scripts/05_run_colmap.sh [data_dir]
# ============================================================
set -e

DATA_DIR="${1:-output}"
COLMAP_DIR="$DATA_DIR/colmap"
DENSE_DIR="$DATA_DIR/colmap_dense"
IMAGES_DIR="$DATA_DIR/images"
PERSP_DIR="$DATA_DIR/openmvs/images"
PERSP_COLMAP="$DATA_DIR/openmvs/colmap_persp"

echo "============================================================"
echo "  COLMAP 3D Dense Reconstruction"
echo "  입력: $COLMAP_DIR"
echo "  이미지: $IMAGES_DIR"
echo "============================================================"

# ── 1. COLMAP 설치 확인 ────────────────────────────────────────
if ! command -v colmap &>/dev/null; then
  echo "[ERROR] COLMAP 미설치. 먼저 실행:"
  echo "  bash scripts/install_colmap_cuda.sh"
  exit 1
fi
echo "[1/6] COLMAP 확인됨: /usr/local/bin/colmap"

# ── 2. 입력 데이터 확인 ────────────────────────────────────────
echo "[2/6] 입력 데이터 확인..."
IMG_COUNT=$(ls "$IMAGES_DIR"/*.jpg 2>/dev/null | wc -l)
echo "  원본 파노라마: $IMG_COUNT 장"

# Perspective 이미지 우선 사용
if [ -d "$PERSP_DIR" ] && [ -d "$PERSP_COLMAP" ]; then
  PERSP_COUNT=$(ls "$PERSP_DIR"/*.jpg 2>/dev/null | wc -l)
  echo "  Perspective 이미지: $PERSP_COUNT 장 → 사용"
  USE_IMAGES="$PERSP_DIR"
  USE_COLMAP="$PERSP_COLMAP"
  USE_MODE="perspective"
else
  echo "  원본 파노라마 이미지 사용"
  USE_IMAGES="$IMAGES_DIR"
  USE_COLMAP="$COLMAP_DIR"
  USE_MODE="panorama"
fi

# ── 3. Dense 작업 디렉토리 준비 ───────────────────────────────
echo "[3/6] 작업 디렉토리 준비..."
rm -rf "$DENSE_DIR"
mkdir -p "$DENSE_DIR/sparse/0"

cp "$USE_COLMAP/cameras.txt"  "$DENSE_DIR/sparse/0/"
cp "$USE_COLMAP/images.txt"   "$DENSE_DIR/sparse/0/"
cp "$USE_COLMAP/points3D.txt" "$DENSE_DIR/sparse/0/"

# ── 4. Image Undistortion ──────────────────────────────────────
echo "[4/6] 이미지 언디스토션..."
colmap image_undistorter \
  --image_path "$USE_IMAGES" \
  --input_path "$DENSE_DIR/sparse/0" \
  --output_path "$DENSE_DIR/dense" \
  --output_type COLMAP \
  --max_image_size 1600 2>&1 | grep -E "Undistorting|Writing|Elapsed|ERROR" | tail -5

# ── 5. patch-match.cfg 자동 생성 ──────────────────────────────
echo "[5/6] patch-match.cfg 생성 (인접 이미지 매핑)..."

python3 - <<PYEOF
import os, json, re

dense_dir = "$DENSE_DIR/dense"
images_dir = os.path.join(dense_dir, "images")
use_mode = "$USE_MODE"

if not os.path.exists(images_dir):
    print(f"[ERROR] {images_dir} 없음")
    exit(1)

# 이미지 목록 수집
imgs = sorted([f for f in os.listdir(images_dir) if f.endswith('.jpg') or f.endswith('.png')])
print(f"[INFO] 이미지 수: {len(imgs)}")

cfg_lines = []

if use_mode == "perspective":
    # Perspective 모드: frame_XXXX_front/back/left/right 구조
    # 각 이미지의 source = 같은 프레임의 다른 방향 + 인접 프레임의 같은 방향
    
    # 프레임 번호별로 그룹화
    frames = {}
    for img in imgs:
        m = re.match(r'(frame_\d+)_(front|back|left|right)', img)
        if m:
            frame_id = m.group(1)
            direction = m.group(2)
            if frame_id not in frames:
                frames[frame_id] = {}
            frames[frame_id][direction] = img
    
    frame_ids = sorted(frames.keys())
    print(f"[INFO] 프레임 수: {len(frame_ids)}")
    
    directions = ['front', 'back', 'left', 'right']
    
    for i, fid in enumerate(frame_ids):
        for d in directions:
            if d not in frames[fid]:
                continue
            ref_img = frames[fid][d]
            sources = []
            
            # 같은 프레임의 다른 방향 (인접 방향)
            for other_d in directions:
                if other_d != d and other_d in frames[fid]:
                    sources.append(frames[fid][other_d])
            
            # 인접 프레임 (앞뒤 2프레임)의 같은 방향
            for delta in [-2, -1, 1, 2]:
                j = i + delta
                if 0 <= j < len(frame_ids):
                    nfid = frame_ids[j]
                    if d in frames[nfid]:
                        sources.append(frames[nfid][d])
            
            if sources:
                cfg_lines.append(ref_img)
                cfg_lines.append(', '.join(sources))

else:
    # 파노라마 모드: frame_XXXX 순서대로 인접 이미지 매핑
    for i, img in enumerate(imgs):
        sources = []
        for delta in [-3, -2, -1, 1, 2, 3]:
            j = i + delta
            if 0 <= j < len(imgs):
                sources.append(imgs[j])
        if sources:
            cfg_lines.append(img)
            cfg_lines.append(', '.join(sources))

cfg_path = os.path.join(dense_dir, "stereo", "patch-match.cfg")
os.makedirs(os.path.dirname(cfg_path), exist_ok=True)

with open(cfg_path, 'w') as f:
    f.write('\n'.join(cfg_lines) + '\n')

print(f"[OK] patch-match.cfg 생성: {len(cfg_lines)//2} 이미지 매핑")
print(f"  경로: {cfg_path}")
PYEOF

# ── 6. PatchMatch Stereo + Fusion + Meshing ────────────────────
echo "[6/6] Dense Reconstruction 실행..."

# CUDA 지원 확인
if colmap patch_match_stereo --help 2>&1 | grep -qi "gpu"; then
    echo "  GPU 모드로 실행 (GTX 1050 Ti)"
    GPU_INDEX=0
else
    echo "  [WARN] GPU 옵션 없음 - CPU 모드"
    GPU_INDEX=-1
fi

echo "  6-1. PatchMatch Stereo (depth map 생성)..."
colmap patch_match_stereo \
  --workspace_path "$DENSE_DIR/dense" \
  --workspace_format COLMAP \
  --PatchMatchStereo.geom_consistency true \
  --PatchMatchStereo.gpu_index $GPU_INDEX \
  --PatchMatchStereo.depth_min 0.01 \
  --PatchMatchStereo.depth_max 10.0 2>&1 | grep -E "Processing|Elapsed|ERROR|WARNING" | tail -20

echo "  6-2. Stereo Fusion (포인트 클라우드 생성)..."
colmap stereo_fusion \
  --workspace_path "$DENSE_DIR/dense" \
  --workspace_format COLMAP \
  --input_type geometric \
  --output_path "$DENSE_DIR/dense/fused.ply" \
  --StereoFusion.min_num_pixels 3 \
  --StereoFusion.max_reproj_error 2.0 2>&1 | grep -E "Fusing|Number|Elapsed|ERROR" | tail -10

# fused.ply 크기 확인
FUSED_SIZE=$(stat -c%s "$DENSE_DIR/dense/fused.ply" 2>/dev/null || echo 0)
echo "  fused.ply 크기: $FUSED_SIZE bytes"

if [ "$FUSED_SIZE" -lt 1000 ]; then
  echo "  [WARN] 포인트 클라우드가 비어있습니다."
  echo "  photometric 모드로 재시도..."
  colmap stereo_fusion \
    --workspace_path "$DENSE_DIR/dense" \
    --workspace_format COLMAP \
    --input_type photometric \
    --output_path "$DENSE_DIR/dense/fused.ply" \
    --StereoFusion.min_num_pixels 2 2>&1 | grep -E "Fusing|Number|Elapsed" | tail -5
  FUSED_SIZE=$(stat -c%s "$DENSE_DIR/dense/fused.ply" 2>/dev/null || echo 0)
  echo "  재시도 후 fused.ply 크기: $FUSED_SIZE bytes"
fi

echo "  6-3. Poisson Meshing (3D 메시 생성)..."
colmap poisson_mesher \
  --input_path "$DENSE_DIR/dense/fused.ply" \
  --output_path "$DENSE_DIR/dense/meshed-poisson.ply" 2>&1 | tail -5

# ── 결과 정리 ─────────────────────────────────────────────────
echo ""
echo "[결과] 파일 복사..."
mkdir -p "$DATA_DIR/mesh"

if [ -f "$DENSE_DIR/dense/meshed-poisson.ply" ]; then
  cp "$DENSE_DIR/dense/meshed-poisson.ply" "$DATA_DIR/mesh/scene_mesh.ply"
  MESH_SIZE=$(stat -c%s "$DATA_DIR/mesh/scene_mesh.ply")
  echo "  ✅ 3D 메시: $DATA_DIR/mesh/scene_mesh.ply ($MESH_SIZE bytes)"
fi
if [ -f "$DENSE_DIR/dense/fused.ply" ]; then
  cp "$DENSE_DIR/dense/fused.ply" "$DATA_DIR/mesh/dense_pointcloud.ply"
  PC_SIZE=$(stat -c%s "$DATA_DIR/mesh/dense_pointcloud.ply")
  echo "  ✅ Dense 포인트 클라우드: $DATA_DIR/mesh/dense_pointcloud.ply ($PC_SIZE bytes)"
fi

# PLY → 웹 뷰어용 JSON 변환
python3 - <<'PYEOF'
import sys, os, struct, json

data_dir = "output"
ply_path = os.path.join(data_dir, 'mesh', 'dense_pointcloud.ply')
out_path = os.path.join(data_dir, 'dense_pointcloud_web.json')

if not os.path.exists(ply_path):
    print(f'[WARN] {ply_path} 없음')
    sys.exit(0)

points, colors = [], []
with open(ply_path, 'rb') as f:
    header_lines = []
    while True:
        line = f.readline().decode('utf-8', errors='ignore').strip()
        header_lines.append(line)
        if line == 'end_header':
            break
    header = '\n'.join(header_lines)
    n_vertex = int([l for l in header_lines if 'element vertex' in l][0].split()[-1])
    is_binary = 'binary_little_endian' in header
    has_color = 'red' in header
    print(f'[INFO] {n_vertex} 포인트, binary={is_binary}, color={has_color}')
    step = max(1, n_vertex // 50000)
    if is_binary:
        fmt = '<fff' + ('BBB' if has_color else '')
        sz = struct.calcsize(fmt)
        for i in range(n_vertex):
            data = f.read(sz)
            if len(data) < sz: break
            vals = struct.unpack(fmt, data)
            if i % step == 0:
                points.append([vals[0], vals[1], vals[2]])
                colors.append([vals[3]/255, vals[4]/255, vals[5]/255] if has_color else [0.5,0.7,0.9])
    else:
        for i, line in enumerate(f):
            if i >= n_vertex: break
            parts = line.decode().split()
            if i % step == 0:
                points.append([float(parts[0]), float(parts[1]), float(parts[2])])
                colors.append([int(parts[3])/255, int(parts[4])/255, int(parts[5])/255] if has_color and len(parts)>=6 else [0.5,0.7,0.9])

with open(out_path, 'w') as f:
    json.dump({'points': points, 'colors': colors}, f)
print(f'[OK] Dense 포인트 클라우드 JSON: {out_path} ({len(points)} 포인트)')
PYEOF

echo ""
echo "============================================================"
echo "  COLMAP 3D 재구성 완료!"
echo "============================================================"
echo ""
echo "  생성된 파일:"
ls -lh "$DATA_DIR/mesh/" 2>/dev/null
echo ""
echo "  웹 뷰어 실행:"
echo "    cd $DATA_DIR && python3 -m http.server 8080"
echo "    브라우저: http://localhost:8080/web/"
