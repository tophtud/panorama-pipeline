#!/usr/bin/env python3
"""
360도 파노라마 영상에서 stella_vSLAM 키프레임에 해당하는 이미지 추출 스크립트

stella_vSLAM 키프레임의 타임스탬프(ts)를 기반으로 영상에서 해당 프레임을 추출합니다.
Insta360 X3 Equirectangular 영상 (3840x1920) 처리.

입력:
  - 파노라마 영상 파일 (MP4, MOV 등)
  - keyframes.json (01_extract_from_msg.py 출력)

출력:
  - output/images/frame_XXXX.jpg (각 키프레임 이미지)

사용법:
  python3 02_extract_frames.py --video input.mp4 --keyframes ../output/keyframes.json --output_dir ../output/images
"""

import argparse
import json
import os
import sys
import numpy as np

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False
    print("[WARN] OpenCV not found. Install with: pip3 install opencv-python")

def extract_frames_by_timestamp(video_path, keyframes, output_dir, margin_sec=0.05):
    """타임스탬프 기반 프레임 추출"""
    if not HAS_CV2:
        print("[ERROR] OpenCV required for frame extraction")
        return False
    
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"[ERROR] Cannot open video: {video_path}")
        return False
    
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps
    
    print(f"[INFO] Video: {video_path}")
    print(f"[INFO] FPS: {fps:.2f}, Total frames: {total_frames}, Duration: {duration:.2f}s")
    
    os.makedirs(output_dir, exist_ok=True)
    
    # 타임스탬프 정규화 (첫 키프레임 기준)
    timestamps = [kf['timestamp'] for kf in keyframes]
    ts_min = min(timestamps)
    ts_normalized = [ts - ts_min for ts in timestamps]
    
    extracted = 0
    for kf, ts_norm in zip(keyframes, ts_normalized):
        # 타임스탬프를 프레임 번호로 변환
        frame_num = int(ts_norm * fps)
        frame_num = max(0, min(frame_num, total_frames - 1))
        
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
        ret, frame = cap.read()
        
        if ret:
            out_path = os.path.join(output_dir, f"frame_{kf['id']:04d}.jpg")
            cv2.imwrite(out_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
            extracted += 1
            if extracted % 10 == 0:
                print(f"[INFO] Extracted {extracted}/{len(keyframes)} frames...")
        else:
            print(f"[WARN] Failed to read frame {frame_num} for KF {kf['id']}")
    
    cap.release()
    print(f"[INFO] Extracted {extracted} frames to {output_dir}")
    return True

def extract_frames_by_index(video_path, keyframes, output_dir, total_video_frames=None):
    """
    타임스탬프 없이 키프레임 인덱스 기반 추출
    (타임스탬프가 영상 시작과 맞지 않을 경우 사용)
    """
    if not HAS_CV2:
        print("[ERROR] OpenCV required")
        return False
    
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"[ERROR] Cannot open video: {video_path}")
        return False
    
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    print(f"[INFO] Video FPS: {fps:.2f}, Total frames: {total_frames}")
    
    # 키프레임 ID를 균등 분포로 영상 프레임에 매핑
    kf_ids = sorted([kf['id'] for kf in keyframes])
    n_kf = len(kf_ids)
    
    # 영상 전체에 균등 분포
    frame_indices = np.linspace(0, total_frames - 1, n_kf, dtype=int)
    kf_to_frame = {kf_id: frame_idx for kf_id, frame_idx in zip(kf_ids, frame_indices)}
    
    os.makedirs(output_dir, exist_ok=True)
    extracted = 0
    
    for kf in keyframes:
        frame_num = kf_to_frame[kf['id']]
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
        ret, frame = cap.read()
        
        if ret:
            out_path = os.path.join(output_dir, f"frame_{kf['id']:04d}.jpg")
            cv2.imwrite(out_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
            extracted += 1
        else:
            print(f"[WARN] Failed to read frame {frame_num}")
    
    cap.release()
    print(f"[INFO] Extracted {extracted} frames (index-based)")
    return True

def create_demo_panoramas(keyframes, output_dir, width=3840, height=1920):
    """
    실제 영상 없이 데모용 파노라마 이미지 생성
    (테스트/개발 목적)
    """
    if not HAS_CV2:
        print("[ERROR] OpenCV required")
        return False
    
    os.makedirs(output_dir, exist_ok=True)
    
    positions = np.array([kf['pos_world'] for kf in keyframes])
    pos_min = positions.min(axis=0)
    pos_max = positions.max(axis=0)
    
    for kf in keyframes:
        # 그라디언트 배경 (위치에 따라 색상 변화)
        pos = np.array(kf['pos_world'])
        norm_pos = (pos - pos_min) / (pos_max - pos_min + 1e-6)
        
        # HSV 색공간으로 파노라마 생성
        img = np.zeros((height, width, 3), dtype=np.uint8)
        
        # 수평 그라디언트 (파노라마 특성)
        for x in range(width):
            angle = x / width * 360
            hue = int((norm_pos[0] * 120 + angle * 0.1) % 180)
            img[:, x] = [hue, 200, 200]
        
        img = cv2.cvtColor(img, cv2.COLOR_HSV2BGR)
        
        # 키프레임 ID 텍스트 추가
        cv2.putText(img, f"KF {kf['id']:04d}", (width//2 - 100, height//2),
                    cv2.FONT_HERSHEY_SIMPLEX, 5, (255, 255, 255), 10)
        cv2.putText(img, f"pos: ({pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f})",
                    (width//2 - 200, height//2 + 150),
                    cv2.FONT_HERSHEY_SIMPLEX, 2, (200, 200, 200), 5)
        
        out_path = os.path.join(output_dir, f"frame_{kf['id']:04d}.jpg")
        # 웹 뷰어 테스트용으로 작은 크기로 저장
        img_small = cv2.resize(img, (1920, 960))
        cv2.imwrite(out_path, img_small, [cv2.IMWRITE_JPEG_QUALITY, 85])
    
    print(f"[INFO] Created {len(keyframes)} demo panoramas in {output_dir}")
    return True

def main():
    parser = argparse.ArgumentParser(
        description='Extract panorama frames from video based on stella_vSLAM keyframes'
    )
    parser.add_argument('--video', '-v', help='Input video file path')
    parser.add_argument('--keyframes', '-k', required=True, help='keyframes.json path')
    parser.add_argument('--output_dir', '-o', default='./images', help='Output directory for frames')
    parser.add_argument('--mode', choices=['timestamp', 'index', 'demo'], default='timestamp',
                        help='Extraction mode: timestamp/index/demo')
    args = parser.parse_args()
    
    # 키프레임 로드
    with open(args.keyframes, 'r') as f:
        keyframes = json.load(f)
    print(f"[INFO] Loaded {len(keyframes)} keyframes")
    
    if args.mode == 'demo':
        print("[INFO] Creating demo panoramas (no video required)")
        create_demo_panoramas(keyframes, args.output_dir)
    elif args.video:
        if args.mode == 'timestamp':
            extract_frames_by_timestamp(args.video, keyframes, args.output_dir)
        else:
            extract_frames_by_index(args.video, keyframes, args.output_dir)
    else:
        print("[ERROR] --video required for timestamp/index mode")
        print("[INFO] Use --mode demo to generate test images without video")
        sys.exit(1)

if __name__ == '__main__':
    main()
