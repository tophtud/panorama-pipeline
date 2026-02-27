# stella_vSLAM → 360° 파노라마 투어 파이프라인

Cupix/Matterport 스타일의 360도 파노라마 가상 투어 시스템 구축을 위한 완전한 파이프라인입니다.

## 시스템 아키텍처

```
[Insta360 X3 영상]
       ↓
[stella_vSLAM]
  - Equirectangular 360° 처리
  - ORB 특징점 추출 및 매칭
  - 루프 클로징 최적화
       ↓
[robot_map.msg] ← 이 파이프라인의 입력
  - 104개 키프레임 (카메라 포즈)
  - 37,840개 3D 랜드마크
  - 카메라: Insta360 X3 (3840×1920)
       ↓
[01_extract_from_msg.py]
  - 쿼터니언 → 회전행렬 변환
  - 카메라 월드 좌표 계산
  - COLMAP 형식 변환
  - PLY 포인트 클라우드 생성
       ↓
[02_extract_frames.py]
  - 타임스탬프 기반 프레임 추출
  - 또는 데모 파노라마 생성
       ↓
[make_mesh_from_pc.py]  ← 3D 메쉬 생성 (Open3D Poisson)
  - pointcloud.ply → scene_mesh.ply
  - 117,924 정점, 227,464 삼각형
       ↓
[웹 파노라마 뷰어 (output/web/index.html)]
  - Three.js 기반 360° 파노라마 렌더링
  - 2D 탑뷰 미니맵 (카메라 경로)
  - 3D 포인트 클라우드 + 메쉬 뷰
  - 키프레임 간 이동 (핫스팟)
  - 자동재생 / 키보드 네비게이션
```

## 데이터 분석 결과 (robot_map.msg)

| 항목 | 값 |
|------|-----|
| 카메라 모델 | Insta360 X3 (Equirectangular) |
| 해상도 | 3840 × 1920 |
| FPS | 30.0 |
| 키프레임 수 | 104개 |
| 랜드마크 수 | 37,840개 |
| 카메라 경로 | U자형 (약 1.7m × 1.8m) |
| 포즈 형식 | 쿼터니언 [qx, qy, qz, qw] + 평행이동 [tx, ty, tz] |

## 빠른 시작

### 1단계: 환경 설정

```bash
pip3 install msgpack numpy opencv-python-headless open3d
```

### 2단계: msg 파일에서 데이터 추출

```bash
python3 scripts/01_extract_from_msg.py \
  --input robot_map.msg \
  --output_dir output \
  --min_obs 3
```

**출력 파일:**
- `output/keyframes.json` - 104개 키프레임 포즈 데이터
- `output/camera_path.json` - 웹 뷰어용 경로 데이터
- `output/pointcloud.ply` - 3D 포인트 클라우드 (PLY)
- `output/pointcloud_web.json` - 웹 뷰어용 포인트 클라우드
- `output/colmap/` - COLMAP 형식 변환 파일

### 3단계: 파노라마 이미지 추출

**실제 영상이 있는 경우 (권장):**
```bash
python3 scripts/02_extract_frames.py \
  --video /path/to/panorama.mp4 \
  --keyframes output/keyframes.json \
  --output_dir output/images \
  --mode timestamp
```

**데모 이미지 생성 (영상 없이 테스트):**
```bash
python3 scripts/02_extract_frames.py \
  --keyframes output/keyframes.json \
  --output_dir output/images \
  --mode demo
```

### 4단계: 3D 메쉬 생성 (Open3D Poisson)

```bash
python3 scripts/make_mesh_from_pc.py
```

**출력:**
- `output/mesh/scene_mesh.ply` - 3D 메쉬 (117,924 정점, 227,464 삼각형)

### 5단계: 웹 뷰어 실행

```bash
bash start_viewer.sh 8080
```

브라우저에서 `http://localhost:8080/web/` 접속

## 웹 뷰어 기능

| 기능 | 설명 |
|------|------|
| 360° 파노라마 | Three.js SphereGeometry 내부 렌더링 |
| 마우스 드래그 | 시점 회전 |
| 마우스 휠 | FOV 줌 인/아웃 |
| 키보드 ←→ | 이전/다음 키프레임 이동 |
| Space | 자동재생 토글 |
| 2D 미니맵 | 카메라 경로 탑뷰 + 클릭 이동 |
| 3D 맵 | 포인트 클라우드 + 3D 메쉬 뷰 |
| 키프레임 목록 | 우측 패널에서 직접 선택 |
| 핫스팟 | 화면 내 이동 버튼 |
| 자동재생 | 1.5초 간격 자동 이동 |
| 메쉬 토글 | 🏗 메시 숨기기/보이기 버튼 |

## 핵심 기술: 좌표계 변환

stella_vSLAM은 카메라-월드 변환(camera-from-world)을 저장합니다:

```python
# 쿼터니언 [qx, qy, qz, qw] → 회전 행렬 R_cw
R_cw = quaternion_to_rotation_matrix(qx, qy, qz, qw)
t_cw = [tx, ty, tz]

# 카메라 월드 위치 계산
# t_wc = -R_cw^T * t_cw
R_wc = R_cw.T
t_wc = -R_wc @ t_cw  # 이것이 카메라의 실제 3D 위치
```

## 파일 구조

```
panorama_pipeline/
├── scripts/
│   ├── 01_extract_from_msg.py    # msg → JSON/PLY/COLMAP
│   ├── 02_extract_frames.py      # 영상 → 키프레임 이미지
│   ├── 03_to_openmvs.py          # Equirect → Perspective
│   ├── 04_run_openmvs.py         # OpenMVS 3D 재구성
│   ├── 05_web_viewer.py          # 웹 서버 실행
│   ├── 06_make_mesh.py           # COLMAP 포인트 → 메쉬
│   └── make_mesh_from_pc.py      # stella_vSLAM 포인트 → 메쉬 (권장)
├── output/
│   ├── keyframes.json            # 키프레임 포즈 데이터
│   ├── camera_path.json          # 웹 뷰어용 경로
│   ├── pointcloud.ply            # 3D 포인트 클라우드
│   ├── pointcloud_web.json       # 웹 뷰어용 포인트 클라우드
│   ├── colmap/                   # COLMAP 형식 파일
│   ├── images/                   # 키프레임 이미지 (실제 영상에서 추출)
│   ├── mesh/
│   │   └── scene_mesh.ply        # 3D 메쉬 (Poisson 재구성)
│   └── web/
│       └── index.html            # 웹 파노라마 뷰어
├── start_viewer.sh               # 웹 뷰어 실행 스크립트
└── README.md
```

## 실제 파노라마 이미지 사용 방법

현재 `output/images/`에는 테스트용 더미 이미지가 있습니다.
실제 Insta360 X3 영상으로 교체하려면:

```bash
# 1. 기존 더미 이미지 삭제
rm output/images/*.jpg

# 2. 실제 영상에서 프레임 추출
python3 scripts/02_extract_frames.py \
  --video /path/to/your/video.mp4 \
  --keyframes output/keyframes.json \
  --output_dir output/images \
  --mode timestamp

# 3. 웹 뷰어 재시작
bash start_viewer.sh 8080
```

## 주의사항

- 파노라마 이미지는 Equirectangular 형식 (가로:세로 = 2:1)이어야 합니다
- 권장 해상도: 3840×1920 또는 1920×960
- 웹 뷰어는 `output/` 디렉토리를 루트로 하는 HTTP 서버가 필요합니다
- 3D 메쉬 파일(`output/mesh/scene_mesh.ply`)이 있어야 메쉬 뷰가 활성화됩니다
