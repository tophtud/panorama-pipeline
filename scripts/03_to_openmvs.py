#!/usr/bin/env python3
"""
stella_vSLAM 데이터를 OpenMVS 입력 형식으로 변환

OpenMVS는 핀홀(Pinhole) 카메라 모델을 기반으로 하므로,
Equirectangular 360도 이미지를 Perspective 투영으로 변환하여 처리합니다.

전략:
  Option A: Equirectangular → 4방향 Perspective 뷰 추출 (전방, 좌, 우, 후방)
  Option B: Equirectangular → 큐브맵 6면 변환

입력:
  - output/keyframes.json     (R_cw, trans_cw 포함)
  - output/camera_path.json   (위치/방향 정보)
  - output/images/            (파노라마 이미지들)

출력:
  - output/openmvs/images/    (변환된 Perspective 이미지들)
  - output/openmvs/colmap/    (COLMAP 형식 파일)
  - output/openmvs/perspective_cameras.json

사용법:
  python3 03_to_openmvs.py --data_dir output --mode perspective --face_size 1024
"""

import argparse
import json
import os
import math
import numpy as np

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False
    print("[WARN] OpenCV not found. Install: pip3 install opencv-python-headless")


def equirect_to_perspective(equirect_img, fov_deg=90, yaw_deg=0, pitch_deg=0,
                             out_width=1024, out_height=1024):
    """
    Equirectangular 이미지를 Perspective(핀홀) 뷰로 변환

    Args:
        equirect_img: 입력 Equirectangular 이미지 (H x W x 3)
        fov_deg: 수평 시야각 (degrees)
        yaw_deg: 수평 회전각 (degrees, 0=전방)
        pitch_deg: 수직 회전각 (degrees, 0=수평)
        out_width, out_height: 출력 이미지 크기

    Returns:
        perspective 이미지 (out_height x out_width x 3)
        intrinsic matrix K (3x3)
    """
    H, W = equirect_img.shape[:2]

    f = out_width / (2 * math.tan(math.radians(fov_deg / 2)))
    cx, cy = out_width / 2.0, out_height / 2.0
    K = np.array([[f, 0, cx], [0, f, cy], [0, 0, 1]])

    u, v = np.meshgrid(np.arange(out_width), np.arange(out_height))
    x = (u - cx) / f
    y = (v - cy) / f
    z = np.ones_like(x)

    norm = np.sqrt(x**2 + y**2 + z**2)
    x, y, z = x / norm, y / norm, z / norm

    yaw   = math.radians(yaw_deg)
    pitch = math.radians(pitch_deg)

    Ry = np.array([[ math.cos(yaw), 0, math.sin(yaw)],
                   [             0, 1,             0],
                   [-math.sin(yaw), 0, math.cos(yaw)]])
    Rx = np.array([[1,              0,               0],
                   [0,  math.cos(pitch), -math.sin(pitch)],
                   [0,  math.sin(pitch),  math.cos(pitch)]])
    R = Ry @ Rx

    dirs = np.stack([x, y, z], axis=-1)
    dirs_rot = dirs @ R.T
    xr, yr, zr = dirs_rot[..., 0], dirs_rot[..., 1], dirs_rot[..., 2]

    lon = np.arctan2(xr, zr)
    lat = np.arcsin(np.clip(yr, -1, 1))

    map_x = ((lon / math.pi + 1) / 2 * W).astype(np.float32)
    map_y = ((0.5 - lat / math.pi) * H).astype(np.float32)

    perspective = cv2.remap(equirect_img, map_x, map_y,
                            cv2.INTER_LINEAR, cv2.BORDER_WRAP)
    return perspective, K


def get_perspective_rotation(yaw_deg, pitch_deg):
    """Perspective 뷰의 추가 회전 행렬"""
    yaw   = math.radians(yaw_deg)
    pitch = math.radians(pitch_deg)
    Ry = np.array([[ math.cos(yaw), 0, math.sin(yaw)],
                   [             0, 1,             0],
                   [-math.sin(yaw), 0, math.cos(yaw)]])
    Rx = np.array([[1,              0,               0],
                   [0,  math.cos(pitch), -math.sin(pitch)],
                   [0,  math.sin(pitch),  math.cos(pitch)]])
    return Ry @ Rx


def rotation_matrix_to_quaternion(R):
    """회전 행렬 → 쿼터니언 [qw, qx, qy, qz]"""
    trace = R[0, 0] + R[1, 1] + R[2, 2]
    if trace > 0:
        s = 0.5 / math.sqrt(trace + 1.0)
        qw = 0.25 / s
        qx = (R[2, 1] - R[1, 2]) * s
        qy = (R[0, 2] - R[2, 0]) * s
        qz = (R[1, 0] - R[0, 1]) * s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = 2.0 * math.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2])
        qw = (R[2, 1] - R[1, 2]) / s
        qx = 0.25 * s
        qy = (R[0, 1] + R[1, 0]) / s
        qz = (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = 2.0 * math.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2])
        qw = (R[0, 2] - R[2, 0]) / s
        qx = (R[0, 1] + R[1, 0]) / s
        qy = 0.25 * s
        qz = (R[1, 2] + R[2, 1]) / s
    else:
        s = 2.0 * math.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1])
        qw = (R[1, 0] - R[0, 1]) / s
        qx = (R[0, 2] + R[2, 0]) / s
        qy = (R[1, 2] + R[2, 1]) / s
        qz = 0.25 * s
    return qw, qx, qy, qz


def process_keyframes_perspective(kf_details_list, images_dir, output_dir,
                                   views=None, face_size=1024):
    """
    각 키프레임의 Equirectangular 이미지를 Perspective 뷰로 변환하고
    해당 카메라 포즈를 계산

    kf_details_list: keyframes.json 에서 로드한 리스트 (R_cw, trans_cw 포함)
    """
    if not HAS_CV2:
        print("[ERROR] OpenCV required for image conversion")
        return None

    if views is None:
        views = [
            (0,   0, 'front'),
            (90,  0, 'right'),
            (180, 0, 'back'),
            (270, 0, 'left'),
        ]

    os.makedirs(output_dir, exist_ok=True)
    persp_images_dir = os.path.join(output_dir, 'images')
    os.makedirs(persp_images_dir, exist_ok=True)

    fov_deg = 90
    f = face_size / (2 * math.tan(math.radians(fov_deg / 2)))
    cx, cy = face_size / 2.0, face_size / 2.0
    K = np.array([[f, 0, cx], [0, f, cy], [0, 0, 1]])

    new_cameras = []

    for kf in kf_details_list:
        kf_id = kf['id']
        src_img_path = os.path.join(images_dir, f"frame_{kf_id:04d}.jpg")

        if not os.path.exists(src_img_path):
            print(f"[WARN] Image not found: {src_img_path}")
            continue

        equirect = cv2.imread(src_img_path)
        if equirect is None:
            print(f"[WARN] Cannot read: {src_img_path}")
            continue

        # keyframes.json 에는 R_cw 와 trans_cw 가 모두 있음
        R_cw   = np.array(kf['R_cw'])       # 3x3
        t_cw   = np.array(kf['trans_cw'])   # 3,

        for yaw_deg, pitch_deg, view_name in views:
            persp_img, _ = equirect_to_perspective(
                equirect, fov_deg=fov_deg,
                yaw_deg=yaw_deg, pitch_deg=pitch_deg,
                out_width=face_size, out_height=face_size
            )

            out_img_name = f"frame_{kf_id:04d}_{view_name}.jpg"
            out_img_path = os.path.join(persp_images_dir, out_img_name)
            cv2.imwrite(out_img_path, persp_img, [cv2.IMWRITE_JPEG_QUALITY, 90])

            # 새 카메라 포즈: 뷰 방향 회전 적용
            R_view   = get_perspective_rotation(yaw_deg, pitch_deg)
            R_new_cw = R_view @ R_cw
            t_new_cw = t_cw.copy()

            new_cameras.append({
                'kf_id':   kf_id,
                'view':    view_name,
                'image':   out_img_name,
                'R_cw':    R_new_cw.tolist(),
                't_cw':    t_new_cw.tolist(),
                'K':       K.tolist(),
                'width':   face_size,
                'height':  face_size,
                'fx': f, 'fy': f, 'cx': cx, 'cy': cy,
            })

        if kf_id % 10 == 0:
            print(f"[INFO] Processed KF {kf_id}/{len(kf_details_list)-1}...")

    print(f"[INFO] Generated {len(new_cameras)} perspective views "
          f"({len(views)} views × {len(kf_details_list)} keyframes)")

    cam_info = {
        'K': K.tolist(),
        'width': face_size,
        'height': face_size,
        'fov_deg': fov_deg,
        'cameras': new_cameras
    }

    cam_info_path = os.path.join(output_dir, 'perspective_cameras.json')
    with open(cam_info_path, 'w') as fp:
        json.dump(cam_info, fp, indent=2)
    print(f"[INFO] Saved camera info: {cam_info_path}")

    return cam_info


def write_colmap_perspective(cam_info, landmarks, output_dir):
    """
    Perspective 뷰 카메라 정보를 COLMAP 형식으로 저장
    InterfaceCOLMAP 도구로 OpenMVS .mvs 파일로 변환 가능
    """
    colmap_dir = os.path.join(output_dir, 'colmap_persp')
    os.makedirs(colmap_dir, exist_ok=True)

    cameras = cam_info['cameras']
    K = np.array(cam_info['K'])
    W, H = cam_info['width'], cam_info['height']

    # cameras.txt
    with open(os.path.join(colmap_dir, 'cameras.txt'), 'w') as fp:
        fp.write("# CAMERA_ID, MODEL, WIDTH, HEIGHT, PARAMS[fx, fy, cx, cy]\n")
        fp.write(f"1 PINHOLE {W} {H} "
                 f"{K[0,0]:.6f} {K[1,1]:.6f} {K[0,2]:.6f} {K[1,2]:.6f}\n")

    # images.txt
    with open(os.path.join(colmap_dir, 'images.txt'), 'w') as fp:
        fp.write("# IMAGE_ID, QW, QX, QY, QZ, TX, TY, TZ, CAMERA_ID, NAME\n")
        fp.write("# POINTS2D[] as (X, Y, POINT3D_ID)\n")
        for i, cam in enumerate(cameras):
            img_id = i + 1
            R = np.array(cam['R_cw'])
            t = np.array(cam['t_cw'])
            qw, qx, qy, qz = rotation_matrix_to_quaternion(R)
            fp.write(f"{img_id} {qw:.10f} {qx:.10f} {qy:.10f} {qz:.10f} "
                     f"{t[0]:.10f} {t[1]:.10f} {t[2]:.10f} 1 {cam['image']}\n")
            fp.write("\n")

    # points3D.txt
    with open(os.path.join(colmap_dir, 'points3D.txt'), 'w') as fp:
        fp.write("# POINT3D_ID, X, Y, Z, R, G, B, ERROR, TRACK[]\n")
        for i, lm in enumerate(landmarks):
            x, y, z = lm['pos_w']
            fp.write(f"{i+1} {x:.6f} {y:.6f} {z:.6f} 128 128 255 1.0\n")

    print(f"[INFO] Saved COLMAP perspective format: {colmap_dir}")
    return colmap_dir


def main():
    parser = argparse.ArgumentParser(
        description='Convert stella_vSLAM Equirectangular data to OpenMVS Perspective format'
    )
    parser.add_argument('--data_dir',  '-d', required=True,
                        help='Data directory (output of step 01)')
    parser.add_argument('--images_dir', '-i',
                        help='Panorama images directory (default: <data_dir>/images)')
    parser.add_argument('--output_dir', '-o',
                        help='Output directory (default: <data_dir>/openmvs)')
    parser.add_argument('--mode', choices=['perspective', 'cubemap'],
                        default='perspective', help='Conversion mode')
    parser.add_argument('--face_size', type=int, default=1024,
                        help='Output perspective image size (pixels)')
    args = parser.parse_args()

    if args.images_dir is None:
        args.images_dir = os.path.join(args.data_dir, 'images')
    if args.output_dir is None:
        args.output_dir = os.path.join(args.data_dir, 'openmvs')

    # ── keyframes.json 로드 (R_cw, trans_cw 포함) ──────────────────────
    kf_detail_path = os.path.join(args.data_dir, 'keyframes.json')
    if not os.path.exists(kf_detail_path):
        print(f"[ERROR] keyframes.json not found: {kf_detail_path}")
        print("[INFO] Run step 01 first: python3 01_extract_from_msg.py ...")
        return

    with open(kf_detail_path, 'r') as fp:
        kf_details = json.load(fp)   # list of dicts, each has R_cw, trans_cw

    print(f"[INFO] Loaded {len(kf_details)} keyframes from keyframes.json")
    print(f"[INFO] Mode: {args.mode}")

    # 뷰 목록 결정
    if args.mode == 'cubemap':
        views = [
            (0,    0, 'front'),
            (90,   0, 'right'),
            (180,  0, 'back'),
            (270,  0, 'left'),
            (0,  -90, 'up'),
            (0,   90, 'down'),
        ]
    else:
        views = [
            (0,   0, 'front'),
            (90,  0, 'right'),
            (180, 0, 'back'),
            (270, 0, 'left'),
        ]

    cam_info = process_keyframes_perspective(
        kf_details, args.images_dir, args.output_dir,
        views=views, face_size=args.face_size
    )

    if cam_info is None:
        print("[ERROR] Conversion failed.")
        return

    # 랜드마크 로드 (COLMAP points3D 생성용)
    landmarks = []
    try:
        import struct
        ply_path = os.path.join(args.data_dir, 'pointcloud.ply')
        if os.path.exists(ply_path):
            # PLY에서 간단히 읽기
            with open(ply_path, 'rb') as fp:
                header = b''
                while True:
                    line = fp.readline()
                    header += line
                    if line.strip() == b'end_header':
                        break
            # JSON 랜드마크 사용
            kf_path2 = os.path.join(args.data_dir, 'keyframes.json')
    except Exception:
        pass

    # COLMAP 형식 저장
    colmap_dir = write_colmap_perspective(cam_info, landmarks, args.output_dir)

    print(f"\n{'='*60}")
    print(f"  OpenMVS 준비 완료!")
    print(f"{'='*60}")
    print(f"  생성된 Perspective 이미지: {args.output_dir}/images/")
    print(f"  COLMAP 형식:               {colmap_dir}/")
    print(f"\n  다음 단계 - OpenMVS 실행:")
    print(f"  InterfaceCOLMAP -i {colmap_dir} -o scene.mvs --image-folder {args.output_dir}/images")
    print(f"  DensifyPointCloud scene.mvs --resolution-level 1")
    print(f"  ReconstructMesh scene_dense.mvs")
    print(f"  TextureMesh scene_dense_mesh.mvs --export-type obj")
    print(f"\n  또는 Docker:")
    print(f"  python3 scripts/04_run_openmvs.py --data_dir {args.data_dir}")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
