# RealityScan 2.1 설치 및 파노라마 파이프라인 연동 가이드

## 1. 시스템 요구사항

| 항목 | 최소 | 권장 |
|------|------|------|
| OS | Ubuntu 22.04 64-bit | Ubuntu 24.04 |
| GPU | NVIDIA GPU 8GB VRAM | NVIDIA RTX 3080 이상 |
| RAM | 16 GB | 32 GB 이상 |
| 저장공간 | 50 GB SSD | 100 GB NVMe SSD |
| CUDA | 11.x | 12.x |

> **참고**: RealityScan 2.1 Linux 버전은 **Wine 번들** 기반으로 동작합니다. GPU가 없으면 CPU 전용 모드로 동작하지만 속도가 매우 느립니다.

---

## 2. 설치 방법

### 2-1. .deb 패키지 설치 (Ubuntu/Debian)

```bash
# 1. 다운로드한 .deb 파일 설치
sudo apt install ~/Downloads/RealityScan-2.1.deb

# 의존성 오류 발생 시
sudo apt-get install -f

# 2. 설치 확인
RealityScan --version
# 또는
/opt/RealityScan/RealityScan --version
```

### 2-2. 의존성 수동 설치 (오류 발생 시)

```bash
sudo apt-get install -y \
    libglib2.0-0 \
    libgl1-mesa-glx \
    libglu1-mesa \
    libxrender1 \
    libxrandr2 \
    libxi6 \
    libxcursor1 \
    libnss3 \
    libasound2 \
    libdbus-1-3 \
    libgtk-3-0 \
    wine64 wine32
```

### 2-3. 설치 경로 확인

```bash
# 일반적인 설치 경로
ls /opt/RealityScan/
ls /usr/bin/RealityScan

# 실행 파일 찾기
which RealityScan
find /opt /usr -name "RealityScan*" -type f 2>/dev/null
```

---

## 3. 파노라마 이미지 → 3D 메쉬 생성

### 방법 A: 자동화 스크립트 사용 (권장)

```bash
# panorama_pipeline 폴더에서 실행
cd ~/뉴딕스\ 작업파일/panorama_pipeline

# 전체 파이프라인 실행 (설치 + 메쉬 생성 + 웹 뷰어 통합)
bash scripts/06_realityscan_pipeline.sh --all \
    --images output/images \
    --output output/mesh \
    --quality 2

# 메쉬 생성만 (이미 설치된 경우)
bash scripts/06_realityscan_pipeline.sh --mesh \
    --images output/images \
    --output output/mesh
```

### 방법 B: CLI 직접 실행

```bash
# 실행 파일 경로 설정 (설치 경로에 맞게 수정)
export PATH=$PATH:/opt/RealityScan

# 파노라마 이미지 폴더 → 3D 메쉬 생성
RealityScan \
    -headless \
    -newScene \
    -addFolder output/images \
    -align \
    -selectMaximalComponent \
    -calculateNormalModel \
    -selectMaximalComponent \
    -unwrap \
    -calculateTexture \
    -exportSelectedModel output/mesh/scene_mesh.glb \
    -save output/realityscan_project.rsproj \
    -quit
```

### 방법 C: .rscmd 배치 파일 사용

```bash
# scripts/panorama_to_mesh.rscmd 파일 사용
RealityScan \
    -execRSCMD scripts/panorama_to_mesh.rscmd \
    "$(pwd)/output/images" \
    "$(pwd)/output/mesh/scene_mesh.glb"
```

---

## 4. 품질 옵션 비교

| 옵션 | 명령어 | 처리 시간 | 결과 품질 | 권장 용도 |
|------|--------|-----------|-----------|-----------|
| Preview | `-calculatePreviewModel` | 5~10분 | 낮음 | 빠른 테스트 |
| Normal | `-calculateNormalModel` | 20~40분 | 중간 | 일반 사용 |
| High | `-calculateHighModel` | 1~3시간 | 높음 | 최종 결과물 |

---

## 5. 웹 뷰어에 3D 메쉬 통합

```bash
# GLB 파일이 생성된 후 웹 뷰어에 통합
python3 scripts/05_realityscan_to_web.py \
    --input output/mesh/scene_mesh.glb \
    --output_dir output/mesh

# 웹 뷰어 실행
bash start_viewer.sh 8080
# → http://localhost:8080/web/ 접속
# → 🗺 3D 맵 버튼 클릭
```

---

## 6. 웹 뷰어 메쉬 자동 로딩 우선순위

웹 뷰어(`output/web/index.html`)는 다음 순서로 메쉬 파일을 자동 탐색합니다:

1. `output/mesh/scene_mesh.glb` ← **RealityScan 기본 출력**
2. `output/mesh/scene_mesh.gltf`
3. `output/mesh/scene_mesh.ply` ← Open3D Poisson 재구성
4. `output/openmvs/scene_dense_mesh_texture.obj`

---

## 7. 경로 포인터 클릭 → 위치 이동 모션 작동 방식

| 입력 | 동작 |
|------|------|
| 미니맵 경로 점 클릭 | 페이드 아웃(200ms) → 해당 KF 파노라마 로드 → 페이드 인 |
| 파노라마 내 `◀ KF N` 핫스팟 클릭 | 인접 키프레임으로 cubic ease-in-out 방향 보간(0.8초) |
| 키프레임 목록 클릭 | 즉시 해당 KF로 이동 |
| 3D 맵 마커 클릭 | 해당 KF 이동 후 파노라마 뷰로 자동 전환 |
| 키보드 `←` `→` | 이전/다음 KF |
| 하단 진행 바 클릭 | 임의 위치 점프 |

---

## 8. 전체 파이프라인 흐름

```
Insta360 X3 영상 (video.mp4)
    ↓
[01] stella_vSLAM
    → output/keyframes.json (카메라 경로)
    → output/pointcloud_web.json (포인트 클라우드)
    ↓
[02] 키프레임 이미지 추출
    → output/images/frame_XXXX.jpg
    ↓
[03] RealityScan 2.1 CLI
    → output/mesh/scene_mesh.glb (텍스처 3D 메쉬)
    ↓
[04] 웹 뷰어 (output/web/index.html)
    ├── 360° 파노라마 뷰어
    ├── 미니맵 (2D 탑뷰 경로)
    ├── 3D 맵 (포인트 클라우드 + RealityScan 메쉬)
    └── 경로 포인터 클릭 → 위치 이동 모션
```

---

## 9. 문제 해결

### "RealityScan: command not found"
```bash
# 설치 경로 확인
find /opt /usr -name "RealityScan" -o -name "RealityScan.exe" 2>/dev/null

# PATH에 추가
echo 'export PATH=$PATH:/opt/RealityScan' >> ~/.bashrc
source ~/.bashrc
```

### "GPU not found" 또는 CUDA 오류
```bash
# NVIDIA 드라이버 확인
nvidia-smi

# CUDA 버전 확인
nvcc --version

# CPU 전용 모드로 실행 (느리지만 동작함)
RealityScan -headless -set "gpuEnabled=false" ...
```

### 이미지 정렬 실패 (align 오류)
```bash
# 이미지 수가 충분한지 확인 (최소 10장 이상 권장)
ls output/images/*.jpg | wc -l

# 이미지 품질 확인 - 흔들림/노출 문제 있는 이미지 제거
# 02_extract_frames.py의 --quality_threshold 옵션 활용
python3 scripts/02_extract_frames.py \
    --video video.mp4 \
    --keyframes output/keyframes.json \
    --output_dir output/images \
    --quality_threshold 0.7
```
