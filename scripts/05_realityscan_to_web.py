#!/usr/bin/env python3
"""
05_realityscan_to_web.py
========================
RealityScan (또는 RealityCapture) 에서 내보낸 3D 메쉬를
파노라마 웹 뷰어의 output/mesh/ 폴더에 복사/변환하는 스크립트.

지원 포맷:
  - GLB / GLTF  (RealityScan 기본 내보내기)
  - OBJ + MTL   (RealityCapture 내보내기)
  - PLY          (포인트 클라우드 or 메쉬)

사용법:
  python3 scripts/05_realityscan_to_web.py \\
      --input /path/to/realityscan_export.glb \\
      --output_dir output/mesh

RealityScan Linux CLI 사용법:
  1. 설치: https://www.realityscan.com/en-US/linux (에픽 계정 필요)
  2. 이미지 폴더로 프로젝트 생성:
       RealityScan.exe -newScene -addFolder /path/to/images
  3. 정렬 + 재구성:
       RealityScan.exe -align -reconstruct
  4. GLB 내보내기:
       RealityScan.exe -exportModel /path/to/output.glb -format glb
  5. 이 스크립트로 웹 뷰어에 통합:
       python3 scripts/05_realityscan_to_web.py \\
           --input /path/to/output.glb \\
           --output_dir output/mesh
"""

import argparse
import shutil
import os
import sys

def main():
    parser = argparse.ArgumentParser(description='RealityScan 메쉬를 웹 뷰어에 통합')
    parser.add_argument('--input', required=True, help='RealityScan 내보내기 파일 경로 (.glb/.gltf/.obj/.ply)')
    parser.add_argument('--output_dir', default='output/mesh', help='출력 디렉토리 (기본: output/mesh)')
    parser.add_argument('--name', default='scene_mesh', help='출력 파일 기본 이름 (기본: scene_mesh)')
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f'[ERROR] 입력 파일이 없습니다: {args.input}')
        sys.exit(1)

    os.makedirs(args.output_dir, exist_ok=True)
    ext = os.path.splitext(args.input)[1].lower()

    # GLB / GLTF: 그대로 복사
    if ext in ('.glb', '.gltf'):
        dst = os.path.join(args.output_dir, f'{args.name}{ext}')
        shutil.copy2(args.input, dst)
        print(f'[OK] GLB/GLTF 복사 완료: {dst}')

        # 텍스처 폴더도 복사 (gltf의 경우)
        src_dir = os.path.dirname(args.input)
        for f in os.listdir(src_dir):
            if f.endswith(('.bin', '.png', '.jpg', '.jpeg')):
                shutil.copy2(os.path.join(src_dir, f), os.path.join(args.output_dir, f))
                print(f'[OK] 텍스처 복사: {f}')

    # OBJ + MTL: 복사 후 MTL 경로 수정
    elif ext == '.obj':
        dst_obj = os.path.join(args.output_dir, f'{args.name}.obj')
        shutil.copy2(args.input, dst_obj)
        print(f'[OK] OBJ 복사 완료: {dst_obj}')

        mtl_path = args.input.replace('.obj', '.mtl')
        if os.path.exists(mtl_path):
            dst_mtl = os.path.join(args.output_dir, f'{args.name}.mtl')
            shutil.copy2(mtl_path, dst_mtl)
            print(f'[OK] MTL 복사 완료: {dst_mtl}')

        # 텍스처 이미지 복사
        src_dir = os.path.dirname(args.input)
        for f in os.listdir(src_dir):
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.tga', '.bmp')):
                shutil.copy2(os.path.join(src_dir, f), os.path.join(args.output_dir, f))
                print(f'[OK] 텍스처 복사: {f}')

    # PLY: 그대로 복사
    elif ext == '.ply':
        dst = os.path.join(args.output_dir, f'{args.name}.ply')
        shutil.copy2(args.input, dst)
        print(f'[OK] PLY 복사 완료: {dst}')

    else:
        print(f'[ERROR] 지원하지 않는 포맷: {ext}')
        print('지원 포맷: .glb, .gltf, .obj, .ply')
        sys.exit(1)

    print()
    print('=' * 50)
    print('웹 뷰어에서 3D 메쉬 확인 방법:')
    print('  1. bash start_viewer.sh 8080')
    print('  2. http://localhost:8080/web/ 접속')
    print('  3. 🗺 3D 맵 버튼 클릭')
    print('=' * 50)

if __name__ == '__main__':
    main()
