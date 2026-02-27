#!/usr/bin/env python3
"""
OpenMVS 3D 재구성 파이프라인 실행 스크립트

로컬에 OpenMVS가 설치되어 있으면 직접 실행하고,
없으면 Docker 명령어를 생성합니다.

사용법:
  python3 04_run_openmvs.py --data_dir output
  python3 04_run_openmvs.py --data_dir output --resolution_level 2  # 빠른 처리
  python3 04_run_openmvs.py --data_dir output --use_docker          # Docker 강제 사용
"""

import argparse
import os
import subprocess
import shutil
import sys

# OpenMVS 실행 파일 목록
OPENMVS_TOOLS = [
    'InterfaceCOLMAP',
    'DensifyPointCloud',
    'ReconstructMesh',
    'RefineMesh',
    'TextureMesh',
]

def find_openmvs():
    """로컬에 설치된 OpenMVS 찾기"""
    found = {}
    search_paths = [
        '/usr/bin', '/usr/local/bin',
        os.path.expanduser('~/.local/bin'),
        '/opt/openmvs/bin',
        os.path.expanduser('~/openmvs_build/openMVS/build/bin'),
    ]

    for tool in OPENMVS_TOOLS:
        # PATH에서 먼저 찾기
        path = shutil.which(tool)
        if path:
            found[tool] = path
            continue
        # 추가 경로에서 찾기
        for sp in search_paths:
            full = os.path.join(sp, tool)
            if os.path.isfile(full) and os.access(full, os.X_OK):
                found[tool] = full
                break

    return found

def check_docker():
    """Docker 사용 가능 여부 확인"""
    try:
        result = subprocess.run(['docker', 'info'],
                                capture_output=True, timeout=5)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False

def run_cmd(cmd, desc=""):
    """명령어 실행 및 결과 확인"""
    print(f"\n[RUN] {desc}")
    print(f"  $ {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=False)
    if result.returncode != 0:
        print(f"[ERROR] 명령 실패 (exit code {result.returncode}): {desc}")
        return False
    return True

def run_with_docker(data_abs, openmvs_dir, colmap_dir, images_dir,
                    resolution_level=1):
    """Docker를 이용한 OpenMVS 실행"""
    print("\n[INFO] Docker를 이용한 OpenMVS 실행")

    # Docker 이미지 확인/다운로드
    print("[INFO] Docker 이미지 확인...")
    subprocess.run(['docker', 'pull', 'cdcseacave/openmvs:latest'])

    base_cmd = [
        'docker', 'run', '--rm',
        '-v', f'{data_abs}:/data',
        'cdcseacave/openmvs'
    ]

    steps = [
        (
            base_cmd + [
                'InterfaceCOLMAP',
                '-i', '/data/openmvs/colmap_persp',
                '-o', '/data/openmvs/scene.mvs',
                '--image-folder', '/data/openmvs/images',
                '-w', '/data/openmvs'
            ],
            "InterfaceCOLMAP: COLMAP → .mvs 변환"
        ),
        (
            base_cmd + [
                'DensifyPointCloud',
                '/data/openmvs/scene.mvs',
                '--resolution-level', str(resolution_level),
                '--number-views', '4',
                '-w', '/data/openmvs'
            ],
            "DensifyPointCloud: 밀집 포인트 클라우드 생성"
        ),
        (
            base_cmd + [
                'ReconstructMesh',
                '/data/openmvs/scene_dense.mvs',
                '-w', '/data/openmvs'
            ],
            "ReconstructMesh: 3D 메시 생성"
        ),
        (
            base_cmd + [
                'TextureMesh',
                '/data/openmvs/scene_dense_mesh.mvs',
                '--export-type', 'obj',
                '-w', '/data/openmvs'
            ],
            "TextureMesh: 텍스처 매핑"
        ),
    ]

    for cmd, desc in steps:
        if not run_cmd(cmd, desc):
            return False

    return True

def run_local(tools, openmvs_dir, colmap_dir, images_dir,
              resolution_level=1):
    """로컬 OpenMVS 실행"""
    print("[INFO] 로컬 OpenMVS 실행")

    steps = [
        (
            [tools['InterfaceCOLMAP'],
             '-i', colmap_dir,
             '-o', os.path.join(openmvs_dir, 'scene.mvs'),
             '--image-folder', images_dir,
             '-w', openmvs_dir],
            "InterfaceCOLMAP"
        ),
        (
            [tools['DensifyPointCloud'],
             os.path.join(openmvs_dir, 'scene.mvs'),
             '--resolution-level', str(resolution_level),
             '--number-views', '4',
             '-w', openmvs_dir],
            "DensifyPointCloud"
        ),
        (
            [tools['ReconstructMesh'],
             os.path.join(openmvs_dir, 'scene_dense.mvs'),
             '-w', openmvs_dir],
            "ReconstructMesh"
        ),
        (
            [tools['TextureMesh'],
             os.path.join(openmvs_dir, 'scene_dense_mesh.mvs'),
             '--export-type', 'obj',
             '-w', openmvs_dir],
            "TextureMesh"
        ),
    ]

    for cmd, desc in steps:
        if not run_cmd(cmd, desc):
            return False

    return True

def print_install_guide():
    """OpenMVS 설치 가이드 출력"""
    print("""
============================================================
  OpenMVS 설치 방법
============================================================

[방법 1] 소스 빌드 (권장, Ubuntu 20.04/22.04)
  bash scripts/install_openmvs.sh

[방법 2] Docker 사용 (간편)
  # Docker 설치 (미설치 시):
  curl -fsSL https://get.docker.com | bash
  sudo usermod -aG docker $USER
  newgrp docker

  # OpenMVS Docker 실행:
  bash scripts/run_openmvs_docker.sh output 1

[방법 3] 이 스크립트로 Docker 강제 실행:
  python3 scripts/04_run_openmvs.py --data_dir output --use_docker

[방법 4] Snap (Ubuntu)
  sudo snap install openmvs   # 일부 버전에서 가능

============================================================
""")

def main():
    parser = argparse.ArgumentParser(
        description='Run OpenMVS 3D reconstruction pipeline'
    )
    parser.add_argument('--data_dir', '-d', default='output',
                        help='Data directory (output of step 03)')
    parser.add_argument('--resolution_level', '-r', type=int, default=1,
                        help='Resolution level: 0=원본, 1=1/2(권장), 2=1/4(빠름)')
    parser.add_argument('--use_docker', action='store_true',
                        help='Docker 강제 사용 (로컬 OpenMVS 무시)')
    args = parser.parse_args()

    data_abs   = os.path.abspath(args.data_dir)
    openmvs_dir = os.path.join(data_abs, 'openmvs')
    colmap_dir  = os.path.join(openmvs_dir, 'colmap_persp')
    images_dir  = os.path.join(openmvs_dir, 'images')

    print("=" * 60)
    print("  OpenMVS 3D 재구성 파이프라인")
    print("=" * 60)
    print(f"  데이터:        {data_abs}")
    print(f"  해상도 레벨:   {args.resolution_level} "
          f"({'원본' if args.resolution_level==0 else f'1/{2**args.resolution_level}'})")

    # 입력 확인
    if not os.path.isdir(colmap_dir):
        print(f"\n[ERROR] COLMAP 데이터 없음: {colmap_dir}")
        print("[INFO] 먼저 실행: python3 scripts/03_to_openmvs.py --data_dir output")
        sys.exit(1)

    img_count = len([f for f in os.listdir(images_dir)
                     if f.endswith('.jpg')]) if os.path.isdir(images_dir) else 0
    print(f"  Perspective 이미지: {img_count}장")

    # ── OpenMVS 실행 방법 결정 ────────────────────────────────
    if not args.use_docker:
        tools = find_openmvs()
        missing = [t for t in ['InterfaceCOLMAP', 'DensifyPointCloud',
                                'ReconstructMesh', 'TextureMesh']
                   if t not in tools]
        if not missing:
            print(f"\n[INFO] 로컬 OpenMVS 발견:")
            for t, p in tools.items():
                print(f"  ✓ {t}: {p}")
            success = run_local(tools, openmvs_dir, colmap_dir, images_dir,
                                args.resolution_level)
        else:
            print(f"\n[WARN] 로컬 OpenMVS 없음: {missing}")
            if check_docker():
                print("[INFO] Docker 사용 가능 → Docker로 실행")
                success = run_with_docker(data_abs, openmvs_dir, colmap_dir,
                                          images_dir, args.resolution_level)
            else:
                print("[WARN] Docker도 없음")
                print_install_guide()
                sys.exit(1)
    else:
        if not check_docker():
            print("[ERROR] Docker를 사용할 수 없습니다.")
            print_install_guide()
            sys.exit(1)
        success = run_with_docker(data_abs, openmvs_dir, colmap_dir,
                                  images_dir, args.resolution_level)

    # ── 결과 확인 ────────────────────────────────────────────
    if success:
        print("\n" + "=" * 60)
        print("  3D 재구성 완료!")
        print("=" * 60)
        for ext in ['*.obj', '*.ply', '*.mvs']:
            import glob
            files = glob.glob(os.path.join(openmvs_dir, ext))
            for f in files:
                size_mb = os.path.getsize(f) / 1024 / 1024
                print(f"  ✓ {os.path.basename(f)} ({size_mb:.1f} MB)")
        print(f"\n  3D 뷰어: meshlab {openmvs_dir}/scene_dense_mesh_texture.obj")
        print(f"  웹 뷰어: python3 scripts/05_web_viewer.py --data_dir {args.data_dir}")
    else:
        print("\n[ERROR] 파이프라인 실패")
        print_install_guide()
        sys.exit(1)

if __name__ == '__main__':
    main()
