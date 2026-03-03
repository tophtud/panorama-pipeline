#!/usr/bin/env python3
"""
08_equirect_to_perspective.py
Equirectangular(360도) 이미지를 Perspective(일반) 이미지 6방향으로 변환
RealityScan은 equirectangular를 직접 지원하지 않으므로 이 변환이 필요

사용법:
    python3 scripts/08_equirect_to_perspective.py \
        --input output/images \
        --output ~/rs_images \
        --fov 90 \
        --directions front back left right up down
"""

import argparse
import os
import math
import numpy as np
from PIL import Image
from pathlib import Path

def equirect_to_perspective(equirect_img, fov_deg, yaw_deg, pitch_deg, out_size=1024):
    """
    Equirectangular 이미지를 특정 방향의 Perspective 이미지로 변환
    
    Args:
        equirect_img: PIL Image (equirectangular)
        fov_deg: 수평 시야각 (degrees), 권장 90
        yaw_deg: 좌우 회전 (0=앞, 90=오른쪽, 180=뒤, 270=왼쪽)
        pitch_deg: 상하 회전 (0=수평, 90=위, -90=아래)
        out_size: 출력 이미지 크기 (픽셀)
    
    Returns:
        PIL Image (perspective)
    """
    img = np.array(equirect_img.convert('RGB'))
    h_eq, w_eq = img.shape[:2]
    
    fov = math.radians(fov_deg)
    yaw = math.radians(yaw_deg)
    pitch = math.radians(pitch_deg)
    
    # 출력 이미지 픽셀 좌표 생성
    f = out_size / (2 * math.tan(fov / 2))
    cx = cy = out_size / 2
    
    x_out, y_out = np.meshgrid(np.arange(out_size), np.arange(out_size))
    
    # Perspective → 3D 방향 벡터
    dx = (x_out - cx) / f
    dy = (y_out - cy) / f
    dz = np.ones_like(dx)
    
    # 정규화
    norm = np.sqrt(dx**2 + dy**2 + dz**2)
    dx, dy, dz = dx/norm, dy/norm, dz/norm
    
    # Pitch 회전 (X축)
    cp, sp = math.cos(pitch), math.sin(pitch)
    dy2 = dy * cp - dz * sp
    dz2 = dy * sp + dz * cp
    dy, dz = dy2, dz2
    
    # Yaw 회전 (Y축)
    cy2, sy = math.cos(yaw), math.sin(yaw)
    dx2 = dx * cy2 + dz * sy
    dz2 = -dx * sy + dz * cy2
    dx, dz = dx2, dz2
    
    # 3D → Equirectangular UV 좌표
    lon = np.arctan2(dx, dz)  # -π ~ π
    lat = np.arcsin(np.clip(dy, -1, 1))  # -π/2 ~ π/2
    
    u = (lon / (2 * math.pi) + 0.5) * w_eq
    v = (0.5 - lat / math.pi) * h_eq
    
    # 바이리니어 샘플링
    u = np.clip(u, 0, w_eq - 1)
    v = np.clip(v, 0, h_eq - 1)
    
    u0 = np.floor(u).astype(int)
    v0 = np.floor(v).astype(int)
    u1 = np.minimum(u0 + 1, w_eq - 1)
    v1 = np.minimum(v0 + 1, h_eq - 1)
    
    wu = (u - u0)[..., np.newaxis]
    wv = (v - v0)[..., np.newaxis]
    
    result = (img[v0, u0] * (1-wu) * (1-wv) +
              img[v0, u1] * wu * (1-wv) +
              img[v1, u0] * (1-wu) * wv +
              img[v1, u1] * wu * wv).astype(np.uint8)
    
    return Image.fromarray(result)


# 6방향 설정 (yaw, pitch)
DIRECTIONS = {
    'front':  (0,    0),
    'back':   (180,  0),
    'left':   (270,  0),
    'right':  (90,   0),
    'up':     (0,    90),
    'down':   (0,   -90),
}

# 대각선 방향 추가 (더 많은 오버랩)
DIRECTIONS_EXTENDED = {
    'front':       (0,    0),
    'front_up':    (0,    45),
    'front_down':  (0,   -45),
    'back':        (180,  0),
    'back_up':     (180,  45),
    'left':        (270,  0),
    'left_up':     (270,  45),
    'right':       (90,   0),
    'right_up':    (90,   45),
    'front_left':  (315,  0),
    'front_right': (45,   0),
    'back_left':   (225,  0),
    'back_right':  (135,  0),
    'up':          (0,    85),
    'down':        (0,   -85),
}


def main():
    parser = argparse.ArgumentParser(description='Equirectangular → Perspective 변환')
    parser.add_argument('--input', default='output/images', help='입력 equirectangular 이미지 폴더')
    parser.add_argument('--output', default=os.path.expanduser('~/rs_images'), help='출력 폴더')
    parser.add_argument('--fov', type=int, default=90, help='수평 시야각 (기본: 90도)')
    parser.add_argument('--size', type=int, default=1024, help='출력 이미지 크기 (기본: 1024)')
    parser.add_argument('--mode', choices=['basic', 'extended'], default='extended',
                        help='basic=6방향, extended=15방향 (더 많은 오버랩)')
    parser.add_argument('--step', type=int, default=3, help='N번째 이미지마다 처리 (기본: 3)')
    args = parser.parse_args()
    
    input_dir = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    directions = DIRECTIONS_EXTENDED if args.mode == 'extended' else DIRECTIONS
    
    images = sorted(input_dir.glob('*.jpg')) + sorted(input_dir.glob('*.png'))
    images = images[::args.step]  # step마다 샘플링
    
    print(f"[INFO] 입력: {len(images)}장 (step={args.step})")
    print(f"[INFO] 방향: {len(directions)}개 ({args.mode} 모드)")
    print(f"[INFO] 출력 예상: {len(images) * len(directions)}장")
    print(f"[INFO] 출력 폴더: {output_dir}")
    print()
    
    total = len(images) * len(directions)
    count = 0
    
    for img_path in images:
        try:
            equirect = Image.open(img_path)
        except Exception as e:
            print(f"[WARN] {img_path.name} 로드 실패: {e}")
            continue
        
        stem = img_path.stem
        
        for dir_name, (yaw, pitch) in directions.items():
            out_name = f"{stem}_{dir_name}.jpg"
            out_path = output_dir / out_name
            
            if out_path.exists():
                count += 1
                continue
            
            persp = equirect_to_perspective(equirect, args.fov, yaw, pitch, args.size)
            persp.save(out_path, 'JPEG', quality=92)
            
            count += 1
            if count % 50 == 0:
                print(f"[{count}/{total}] {out_name}")
    
    print(f"\n[완료] {count}장 생성 → {output_dir}")
    print()
    print("=" * 60)
    print("RealityScan 설정 (중요!):")
    print("=" * 60)
    print(f"  이미지 폴더: {output_dir}")
    print(f"  Prior Calibration → Prior: Fixed")
    print(f"  Focal Length: {int(1024 / (2 * math.tan(math.radians(args.fov) / 2)))} px")
    print(f"  Prior Lens Distortion → Prior: Fixed")
    print("=" * 60)


if __name__ == '__main__':
    main()
