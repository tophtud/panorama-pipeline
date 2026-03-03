# RealityScan Linux 설치 및 파노라마 파이프라인 연동 가이드

## 1. RealityScan Linux 시스템 요구사항

| 항목 | 최소 | 권장 |
|------|------|------|
| OS | Ubuntu 22.04 64-bit | Ubuntu 24.04 (Kernel 6.14) |
| GPU | NVIDIA GPU 8GB VRAM | NVIDIA RTX 3080 이상 |
| RAM | 16 GB | 32 GB 이상 |
| 저장공간 | 50 GB | 100 GB SSD |

> **참고**: RealityScan Linux는 Wine 기반 실험적 빌드입니다. CLI 전용으로 사용하는 것을 권장합니다.

---

## 2. 설치 방법

### 방법 A: 에픽게임즈 런처 (Windows)
1. [에픽게임즈 런처](https://store.epicgames.com/ko/download) 설치
2. 언리얼 엔진 섹션 → **리얼리티스캔** 탭 → 설치 클릭
3. 설치 후 `EpicInstaller-19.2.0-unrealEngine-*.msi` 실행

### 방법 B: Linux 직접 설치
```bash
# 1. 에픽 계정으로 다운로드 (로그인 필요)
# https://www.realityscan.com/en-US/linux

# 2. 패키지 설치
sudo dpkg -i realityscan_*.deb
# 또는
sudo rpm -i realityscan_*.rpm

# 3. 의존성 설치 (Wine 환경)
sudo apt-get install -f
```

### 방법 C: Heroic Games Launcher (Linux)
```bash
# Heroic 설치
sudo apt install heroic

# 에픽 계정 로그인 후 RealityScan 설치
```

---

## 3. 파노라마 이미지로 3D 메쉬 생성

### 3-1. 이미지 준비
```bash
# stella_vSLAM 키프레임 이미지 추출
python3 scripts/02_extract_frames.py \
  --video /path/to/video.mp4 \
  --keyframes output/keyframes.json \
  --output_dir output/images \
  --mode timestamp
```

### 3-2. RealityScan CLI로 3D 재구성
```bash
# RealityScan 설치 경로 (예시)
RSCAN=/opt/RealityScan/RealityScan.exe

# 새 프로젝트 생성 및 이미지 추가
$RSCAN -newScene myproject.rsproj \
       -addFolder output/images

# 이미지 정렬 (카메라 포즈 추정)
$RSCAN -scene myproject.rsproj -align

# 3D 재구성 (고밀도 포인트 클라우드 + 메쉬)
$RSCAN -scene myproject.rsproj -reconstruct

# GLB 포맷으로 내보내기 (웹 뷰어 최적)
$RSCAN -scene myproject.rsproj \
       -exportModel output/mesh/scene_mesh.glb \
       -format glb \
       -textureQuality high
```

### 3-3. 웹 뷰어에 통합
```bash
# 자동 통합 스크립트 사용
python3 scripts/05_realityscan_to_web.py \
  --input output/mesh/scene_mesh.glb \
  --output_dir output/mesh

# 웹 뷰어 실행
bash start_viewer.sh 8080
```

---

## 4. 웹 뷰어 기능 설명

### 경로 포인터 클릭 → 위치 이동 모션

| 입력 방법 | 동작 |
|-----------|------|
| 미니맵 점 클릭 | 해당 키프레임으로 페이드 전환 + 카메라 방향 보간 |
| 파노라마 내 핫스팟 클릭 | 인접 키프레임으로 이동 |
| 3D 맵 마커 클릭 | 해당 위치로 이동 후 파노라마 뷰로 전환 |
| 키프레임 목록 클릭 | 목록에서 직접 선택 이동 |
| 키보드 ← → | 이전/다음 키프레임 |
| 진행 바 클릭 | 임의 위치로 점프 |

### 3D 맵 메쉬 지원 포맷 (우선순위)
1. `output/mesh/scene_mesh.glb` — RealityScan 기본 내보내기
2. `output/mesh/scene_mesh.gltf` — GLTF 포맷
3. `output/mesh/scene_mesh.ply` — Poisson 재구성 메쉬
4. `output/openmvs/scene_dense_mesh_texture.obj` — OpenMVS 텍스처 메쉬

---

## 5. 대안 포토그래메트리 도구 (Linux 지원)

RealityScan 대신 사용 가능한 오픈소스 도구:

| 도구 | 특징 | 설치 |
|------|------|------|
| **AliceVision Meshroom** | 완전 오픈소스, GUI 지원 | `sudo snap install meshroom` |
| **OpenDroneMap (ODM)** | Docker 기반, 대규모 처리 | `docker run opendronemap/odm` |
| **COLMAP** | 학술용 SfM, CLI | `sudo apt install colmap` |
| **OpenMVS** | 고품질 메쉬 재구성 | 소스 빌드 필요 |

### Meshroom 사용 예시
```bash
# 설치
sudo snap install meshroom

# CLI 실행
meshroom_batch \
  --input output/images/ \
  --output output/mesh/ \
  --save output/mesh/project.mg
```

---

## 6. 파이프라인 전체 흐름

```
Insta360 X3 영상
    ↓
stella_vSLAM → 키프레임 + 카메라 경로 + 포인트 클라우드
    ↓
RealityScan / Meshroom → 고품질 3D 메쉬 (GLB)
    ↓
05_realityscan_to_web.py → output/mesh/scene_mesh.glb
    ↓
웹 뷰어 (index.html)
  ├── 360° 파노라마 뷰 (키프레임 이미지)
  ├── 미니맵 (2D 탑뷰 경로)
  ├── 3D 맵 (포인트 클라우드 + 메쉬)
  └── 경로 포인터 클릭 → 위치 이동 모션
```
