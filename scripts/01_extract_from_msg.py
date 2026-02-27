#!/usr/bin/env python3
"""
stella_vSLAM .msg 파일에서 카메라 포즈(키프레임) 및 3D 포인트 클라우드 추출 스크립트

입력:  stella_vSLAM map database (.msg, MessagePack 형식)
출력:
  - keyframes.json       : 키프레임 ID, 타임스탬프, 월드 좌표 위치, 회전 행렬
  - pointcloud.ply       : 3D 랜드마크 포인트 클라우드 (PLY 형식)
  - camera_path.json     : 순서대로 정렬된 카메라 경로 (웹 뷰어용)
  - colmap/cameras.txt   : COLMAP 형식 카메라 내부 파라미터
  - colmap/images.txt    : COLMAP 형식 카메라 외부 파라미터 (포즈)
  - colmap/points3D.txt  : COLMAP 형식 3D 포인트

사용법:
  python3 01_extract_from_msg.py --input robot_map.msg --output_dir ../output
"""

import argparse
import json
import os
import struct
import sys
import numpy as np
import msgpack

def quaternion_to_rotation_matrix(qx, qy, qz, qw):
    """쿼터니언을 3x3 회전 행렬로 변환 (R_cw: camera-from-world)"""
    R = np.array([
        [1 - 2*(qy**2 + qz**2),     2*(qx*qy - qz*qw),     2*(qx*qz + qy*qw)],
        [    2*(qx*qy + qz*qw), 1 - 2*(qx**2 + qz**2),     2*(qy*qz - qx*qw)],
        [    2*(qx*qz - qy*qw),     2*(qy*qz + qx*qw), 1 - 2*(qx**2 + qy**2)]
    ])
    return R

def rotation_matrix_to_quaternion(R):
    """3x3 회전 행렬을 쿼터니언으로 변환"""
    trace = R[0,0] + R[1,1] + R[2,2]
    if trace > 0:
        s = 0.5 / np.sqrt(trace + 1.0)
        w = 0.25 / s
        x = (R[2,1] - R[1,2]) * s
        y = (R[0,2] - R[2,0]) * s
        z = (R[1,0] - R[0,1]) * s
    elif R[0,0] > R[1,1] and R[0,0] > R[2,2]:
        s = 2.0 * np.sqrt(1.0 + R[0,0] - R[1,1] - R[2,2])
        w = (R[2,1] - R[1,2]) / s
        x = 0.25 * s
        y = (R[0,1] + R[1,0]) / s
        z = (R[0,2] + R[2,0]) / s
    elif R[1,1] > R[2,2]:
        s = 2.0 * np.sqrt(1.0 + R[1,1] - R[0,0] - R[2,2])
        w = (R[0,2] - R[2,0]) / s
        x = (R[0,1] + R[1,0]) / s
        y = 0.25 * s
        z = (R[1,2] + R[2,1]) / s
    else:
        s = 2.0 * np.sqrt(1.0 + R[2,2] - R[0,0] - R[1,1])
        w = (R[1,0] - R[0,1]) / s
        x = (R[0,2] + R[2,0]) / s
        y = (R[1,2] + R[2,1]) / s
        z = 0.25 * s
    return np.array([x, y, z, w])

def load_msg_file(msg_path):
    """stella_vSLAM .msg 파일 로드"""
    print(f"[INFO] Loading {msg_path} ...")
    with open(msg_path, 'rb') as f:
        data = msgpack.unpack(f, raw=False, strict_map_key=False)
    print(f"[INFO] Loaded: {len(data['keyframes'])} keyframes, {len(data['landmarks'])} landmarks")
    return data

def extract_keyframes(data):
    """키프레임에서 카메라 포즈 추출"""
    keyframes = []
    kf_keys = sorted(data['keyframes'].keys(), key=lambda x: int(x))
    
    for kid in kf_keys:
        kf = data['keyframes'][kid]
        rot_cw = kf['rot_cw']   # [qx, qy, qz, qw]
        trans_cw = kf['trans_cw']  # [tx, ty, tz]
        ts = kf.get('ts', 0.0)
        
        qx, qy, qz, qw = rot_cw
        R_cw = quaternion_to_rotation_matrix(qx, qy, qz, qw)
        t_cw = np.array(trans_cw)
        
        # 카메라 월드 좌표: t_wc = -R_cw^T * t_cw
        R_wc = R_cw.T
        t_wc = -R_wc @ t_cw
        
        # 카메라 전방 방향 (월드 좌표계에서 카메라가 바라보는 방향)
        # SLAM에서 카메라 Z축이 전방
        forward_world = R_wc @ np.array([0, 0, 1])
        
        keyframes.append({
            'id': int(kid),
            'timestamp': ts,
            'pos_world': t_wc.tolist(),           # 월드 좌표 위치 [x, y, z]
            'forward_world': forward_world.tolist(), # 전방 방향 벡터
            'rot_cw_quat': rot_cw,                 # 원본 쿼터니언 [qx, qy, qz, qw]
            'trans_cw': trans_cw,                  # 원본 평행이동
            'R_cw': R_cw.tolist(),                 # 회전 행렬 (camera-from-world)
            'n_keypts': kf.get('n_keypts', 0),
            'span_parent': kf.get('span_parent', -1),
            'span_children': kf.get('span_children', []),
            'loop_edges': kf.get('loop_edges', []),
            'lm_ids': kf.get('lm_ids', []),
        })
    
    return keyframes

def extract_landmarks(data, min_observations=3):
    """랜드마크(3D 포인트) 추출 및 필터링"""
    landmarks = []
    for lk, lm in data['landmarks'].items():
        if lm['n_fnd'] >= min_observations:
            landmarks.append({
                'id': int(lk),
                'pos_w': lm['pos_w'],           # 3D 위치 [x, y, z]
                'n_visible': lm['n_vis'],        # 관측 가능 횟수
                'n_found': lm['n_fnd'],          # 실제 관측 횟수
                'ref_keyframe': lm['ref_keyfrm'], # 참조 키프레임
                'first_keyframe': lm['1st_keyfrm'],
            })
    
    print(f"[INFO] Extracted {len(landmarks)} landmarks (min_obs={min_observations})")
    return landmarks

def save_keyframes_json(keyframes, output_dir):
    """키프레임 정보를 JSON으로 저장"""
    out_path = os.path.join(output_dir, 'keyframes.json')
    with open(out_path, 'w') as f:
        json.dump(keyframes, f, indent=2)
    print(f"[INFO] Saved keyframes: {out_path}")

def save_camera_path_json(keyframes, output_dir):
    """웹 뷰어용 카메라 경로 JSON 저장"""
    path_data = {
        'total_keyframes': len(keyframes),
        'camera_model': 'Equirectangular',
        'image_width': 3840,
        'image_height': 1920,
        'keyframes': []
    }
    
    for kf in keyframes:
        path_data['keyframes'].append({
            'id': kf['id'],
            'timestamp': kf['timestamp'],
            'position': {
                'x': kf['pos_world'][0],
                'y': kf['pos_world'][1],
                'z': kf['pos_world'][2]
            },
            'forward': {
                'x': kf['forward_world'][0],
                'y': kf['forward_world'][1],
                'z': kf['forward_world'][2]
            },
            'image_file': f'frame_{kf["id"]:04d}.jpg',
            'n_keypts': kf['n_keypts']
        })
    
    out_path = os.path.join(output_dir, 'camera_path.json')
    with open(out_path, 'w') as f:
        json.dump(path_data, f, indent=2)
    print(f"[INFO] Saved camera path: {out_path}")

def save_pointcloud_ply(landmarks, output_dir):
    """3D 포인트 클라우드를 PLY 형식으로 저장"""
    out_path = os.path.join(output_dir, 'pointcloud.ply')
    
    # 이상치 제거 (3-sigma)
    pts = np.array([lm['pos_w'] for lm in landmarks])
    mean = pts.mean(axis=0)
    std = pts.std(axis=0)
    mask = np.all(np.abs(pts - mean) < 3 * std, axis=1)
    filtered_lms = [lm for lm, m in zip(landmarks, mask) if m]
    
    print(f"[INFO] Point cloud: {len(filtered_lms)} points after outlier removal (from {len(landmarks)})")
    
    with open(out_path, 'w') as f:
        f.write("ply\n")
        f.write("format ascii 1.0\n")
        f.write(f"element vertex {len(filtered_lms)}\n")
        f.write("property float x\n")
        f.write("property float y\n")
        f.write("property float z\n")
        f.write("property uchar red\n")
        f.write("property uchar green\n")
        f.write("property uchar blue\n")
        f.write("end_header\n")
        
        for lm in filtered_lms:
            x, y, z = lm['pos_w']
            # 관측 빈도에 따라 색상 (파란색 계열)
            intensity = min(255, int(lm['n_found'] * 10))
            f.write(f"{x:.6f} {y:.6f} {z:.6f} {intensity} {intensity} 255\n")
    
    print(f"[INFO] Saved point cloud: {out_path}")
    return filtered_lms

def save_colmap_format(keyframes, landmarks, camera_info, output_dir):
    """
    COLMAP 형식으로 저장 (OpenMVS 입력용)
    
    COLMAP cameras.txt 형식:
      CAMERA_ID, MODEL, WIDTH, HEIGHT, PARAMS[]
    
    COLMAP images.txt 형식:
      IMAGE_ID, QW, QX, QY, QZ, TX, TY, TZ, CAMERA_ID, NAME
      POINTS2D[] as (X, Y, POINT3D_ID)
    
    COLMAP points3D.txt 형식:
      POINT3D_ID, X, Y, Z, R, G, B, ERROR, TRACK[] as (IMAGE_ID, POINT2D_IDX)
    """
    colmap_dir = os.path.join(output_dir, 'colmap')
    os.makedirs(colmap_dir, exist_ok=True)
    
    # --- cameras.txt ---
    # Equirectangular 카메라는 COLMAP에서 직접 지원하지 않으므로
    # SPHERICAL 모델 또는 FULL_OPENCV로 근사
    # OpenMVS는 핀홀 카메라를 기준으로 하므로, 
    # 360도 이미지를 큐브맵으로 변환하거나 SPHERICAL 모델 사용
    cam_path = os.path.join(colmap_dir, 'cameras.txt')
    with open(cam_path, 'w') as f:
        f.write("# Camera list with one line of data per camera:\n")
        f.write("#   CAMERA_ID, MODEL, WIDTH, HEIGHT, PARAMS[]\n")
        f.write("# Number of cameras: 1\n")
        # SPHERICAL 모델: 파라미터 없음 (단위 구면 투영)
        f.write(f"1 SPHERICAL {camera_info['cols']} {camera_info['rows']}\n")
    print(f"[INFO] Saved COLMAP cameras: {cam_path}")
    
    # --- images.txt ---
    img_path = os.path.join(colmap_dir, 'images.txt')
    
    # 랜드마크 ID -> 인덱스 매핑
    lm_id_to_idx = {lm['id']: i+1 for i, lm in enumerate(landmarks)}
    
    with open(img_path, 'w') as f:
        f.write("# Image list with two lines of data per image:\n")
        f.write("#   IMAGE_ID, QW, QX, QY, QZ, TX, TY, TZ, CAMERA_ID, NAME\n")
        f.write("#   POINTS2D[] as (X, Y, POINT3D_ID)\n")
        f.write(f"# Number of images: {len(keyframes)}\n")
        
        for kf in keyframes:
            img_id = kf['id'] + 1  # COLMAP은 1-indexed
            qx, qy, qz, qw = kf['rot_cw_quat']
            tx, ty, tz = kf['trans_cw']
            img_name = f"frame_{kf['id']:04d}.jpg"
            
            # COLMAP 형식: QW, QX, QY, QZ (w-first)
            f.write(f"{img_id} {qw:.10f} {qx:.10f} {qy:.10f} {qz:.10f} "
                    f"{tx:.10f} {ty:.10f} {tz:.10f} 1 {img_name}\n")
            
            # 2D 키포인트 라인 (빈 줄 또는 실제 포인트)
            # lm_ids와 undist_keypts를 매칭하여 작성
            # (실제 구현에서는 원본 이미지에서 추출 필요)
            f.write("\n")
    
    print(f"[INFO] Saved COLMAP images: {img_path}")
    
    # --- points3D.txt ---
    pts_path = os.path.join(colmap_dir, 'points3D.txt')
    with open(pts_path, 'w') as f:
        f.write("# 3D point list with one line of data per point:\n")
        f.write("#   POINT3D_ID, X, Y, Z, R, G, B, ERROR, TRACK[] as (IMAGE_ID, POINT2D_IDX)\n")
        f.write(f"# Number of points: {len(landmarks)}\n")
        
        for i, lm in enumerate(landmarks):
            pt_id = i + 1
            x, y, z = lm['pos_w']
            r, g, b = 128, 128, 255  # 기본 색상
            error = 1.0
            # 참조 키프레임 트랙
            ref_img_id = lm['ref_keyframe'] + 1
            f.write(f"{pt_id} {x:.6f} {y:.6f} {z:.6f} {r} {g} {b} {error:.4f} "
                    f"{ref_img_id} 0\n")
    
    print(f"[INFO] Saved COLMAP points3D: {pts_path}")

def save_openmvs_scene_info(keyframes, landmarks, camera_info, output_dir):
    """
    OpenMVS 입력을 위한 씬 정보 JSON 저장
    (InterfaceCOLMAP 또는 InterfaceOpenMVG 대신 직접 변환 시 사용)
    """
    scene = {
        'camera': {
            'model': camera_info['model_type'],
            'width': camera_info['cols'],
            'height': camera_info['rows'],
            'fps': camera_info['fps'],
        },
        'num_keyframes': len(keyframes),
        'num_landmarks': len(landmarks),
        'keyframes': [
            {
                'id': kf['id'],
                'image': f"frame_{kf['id']:04d}.jpg",
                'pos_world': kf['pos_world'],
                'rot_cw': kf['rot_cw_quat'],
                'trans_cw': kf['trans_cw'],
            }
            for kf in keyframes
        ],
        'sparse_points': [
            {
                'id': lm['id'],
                'pos': lm['pos_w'],
                'n_obs': lm['n_found'],
            }
            for lm in landmarks[:10000]  # 상위 10000개만 (파일 크기 제한)
        ]
    }
    
    out_path = os.path.join(output_dir, 'openmvs_scene_info.json')
    with open(out_path, 'w') as f:
        json.dump(scene, f, indent=2)
    print(f"[INFO] Saved OpenMVS scene info: {out_path}")

def print_statistics(keyframes, landmarks, data):
    """추출 결과 통계 출력"""
    positions = np.array([kf['pos_world'] for kf in keyframes])
    pts = np.array([lm['pos_w'] for lm in landmarks])
    
    print("\n" + "="*60)
    print("EXTRACTION STATISTICS")
    print("="*60)
    print(f"Camera Model  : {data['cameras']['Insta360 X3']['model_type']}")
    print(f"Resolution    : {data['cameras']['Insta360 X3']['cols']} x {data['cameras']['Insta360 X3']['rows']}")
    print(f"FPS           : {data['cameras']['Insta360 X3']['fps']}")
    print(f"Keyframes     : {len(keyframes)}")
    print(f"Landmarks     : {len(landmarks)}")
    print()
    print("Camera Path Extent:")
    print(f"  X: {positions[:,0].min():.4f} ~ {positions[:,0].max():.4f} m")
    print(f"  Y: {positions[:,1].min():.4f} ~ {positions[:,1].max():.4f} m")
    print(f"  Z: {positions[:,2].min():.4f} ~ {positions[:,2].max():.4f} m")
    print()
    print("Point Cloud Extent (before outlier removal):")
    print(f"  X: {pts[:,0].min():.4f} ~ {pts[:,0].max():.4f} m")
    print(f"  Y: {pts[:,1].min():.4f} ~ {pts[:,1].max():.4f} m")
    print(f"  Z: {pts[:,2].min():.4f} ~ {pts[:,2].max():.4f} m")
    print("="*60)

def main():
    parser = argparse.ArgumentParser(
        description='Extract camera poses and point cloud from stella_vSLAM .msg file'
    )
    parser.add_argument('--input', '-i', required=True, help='Input .msg file path')
    parser.add_argument('--output_dir', '-o', default='./output', help='Output directory')
    parser.add_argument('--min_obs', type=int, default=3, help='Minimum landmark observations')
    args = parser.parse_args()
    
    os.makedirs(args.output_dir, exist_ok=True)
    
    # 1. 파일 로드
    data = load_msg_file(args.input)
    
    # 2. 카메라 정보
    camera_info = data['cameras']['Insta360 X3']
    
    # 3. 키프레임 추출
    keyframes = extract_keyframes(data)
    
    # 4. 랜드마크 추출
    landmarks = extract_landmarks(data, min_observations=args.min_obs)
    
    # 5. 통계 출력
    print_statistics(keyframes, landmarks, data)
    
    # 6. 저장
    save_keyframes_json(keyframes, args.output_dir)
    save_camera_path_json(keyframes, args.output_dir)
    filtered_landmarks = save_pointcloud_ply(landmarks, args.output_dir)
    save_colmap_format(keyframes, filtered_landmarks, camera_info, args.output_dir)
    save_openmvs_scene_info(keyframes, filtered_landmarks, camera_info, args.output_dir)
    
    print(f"\n[DONE] All outputs saved to: {args.output_dir}")
    print("\nNext steps:")
    print("  1. Extract panorama frames from video: python3 02_extract_frames.py")
    print("  2. Convert to OpenMVS format:          python3 03_to_openmvs.py")
    print("  3. Run dense reconstruction:           python3 04_run_openmvs.py")
    print("  4. Launch web viewer:                  python3 05_web_viewer.py")

if __name__ == '__main__':
    main()
