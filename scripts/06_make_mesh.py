#!/usr/bin/env python3
"""
fused.ply → 다운샘플링 → Poisson Meshing → scene_mesh.ply
Open3D 기반으로 COLMAP Poisson Mesher Segfault 문제를 우회합니다.

실행: python3 scripts/06_make_mesh.py [--data_dir output] [--max_points 2000000]
"""
import sys, os, json, struct, argparse
import numpy as np

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--data_dir', default='output')
    p.add_argument('--max_points', type=int, default=2000000,
                   help='다운샘플링 후 최대 포인트 수 (기본 200만)')
    p.add_argument('--depth', type=int, default=9,
                   help='Poisson octree depth (기본 9, 높을수록 정밀)')
    p.add_argument('--web_points', type=int, default=50000,
                   help='웹 뷰어용 JSON 최대 포인트 수')
    p.add_argument('--voxel_size', type=float, default=0.0,
                   help='Voxel 크기 직접 지정 (0이면 자동 계산)')
    return p.parse_args()

def main():
    args = parse_args()

    ply_path = os.path.join(args.data_dir, 'colmap_dense', 'dense', 'fused.ply')
    mesh_dir = os.path.join(args.data_dir, 'mesh')
    mesh_path = os.path.join(mesh_dir, 'scene_mesh.ply')
    web_json_path = os.path.join(args.data_dir, 'dense_pointcloud_web.json')

    os.makedirs(mesh_dir, exist_ok=True)

    if not os.path.exists(ply_path):
        print(f'[ERROR] {ply_path} 없음')
        sys.exit(1)

    try:
        import open3d as o3d
        print('[INFO] Open3D 사용')

        print(f'[1/5] PLY 로드 중...')
        pcd = o3d.io.read_point_cloud(ply_path)
        n_orig = len(pcd.points)
        print(f'[INFO] 원본 포인트: {n_orig:,}')

        # 포인트 분포 확인
        pts = np.asarray(pcd.points)
        bbox_min = pts.min(axis=0)
        bbox_max = pts.max(axis=0)
        bbox_size = bbox_max - bbox_min
        print(f'[INFO] 바운딩 박스: {bbox_size}')
        print(f'[INFO] 좌표 범위: x=[{bbox_min[0]:.1f}, {bbox_max[0]:.1f}], '
              f'y=[{bbox_min[1]:.1f}, {bbox_max[1]:.1f}], '
              f'z=[{bbox_min[2]:.1f}, {bbox_max[2]:.1f}]')

        # 좌표 스케일 확인 (너무 크면 정규화)
        scale_factor = 1.0
        max_extent = float(bbox_size.max())
        if max_extent > 10000:
            # 스케일이 너무 큼 - 정규화 (예: mm → m 변환)
            scale_factor = 1.0 / max_extent * 10.0  # 최대 10m 범위로 정규화
            print(f'[INFO] 좌표 스케일 정규화: factor={scale_factor:.6f} (max_extent={max_extent:.1f})')
            pcd_scaled = o3d.geometry.PointCloud()
            pcd_scaled.points = o3d.utility.Vector3dVector(pts * scale_factor)
            if pcd.has_colors():
                pcd_scaled.colors = pcd.colors
            pcd = pcd_scaled
            pts = np.asarray(pcd.points)
            bbox_size = pts.max(axis=0) - pts.min(axis=0)
            print(f'[INFO] 정규화 후 바운딩 박스: {bbox_size}')

        print(f'[2/5] 다운샘플링 ({args.max_points:,} 포인트로)...')
        if n_orig > args.max_points:
            if args.voxel_size > 0:
                voxel_size = args.voxel_size
            else:
                # 포인트 밀도 기반 Voxel 크기 계산
                # 목표 포인트 수에 맞는 Voxel 크기 추정
                volume = float(bbox_size[0] * bbox_size[1] * bbox_size[2])
                if volume > 0:
                    # 각 Voxel이 평균 (n_orig / max_points)개 포인트를 포함하도록
                    pts_per_voxel = n_orig / args.max_points
                    voxel_size = (volume / args.max_points) ** (1/3)
                    # 최소 0.001, 최대 bbox의 1% 로 클램핑
                    voxel_size = max(0.001, min(voxel_size, float(bbox_size.max()) * 0.01))
                else:
                    voxel_size = 0.05
            print(f'[INFO] Voxel 크기: {voxel_size:.4f}')
            pcd_down = pcd.voxel_down_sample(voxel_size=voxel_size)
            n_down = len(pcd_down.points)
            print(f'[INFO] 다운샘플링 후: {n_down:,} 포인트')

            # 여전히 너무 많으면 랜덤 샘플링
            if n_down > args.max_points:
                pcd_down = pcd_down.random_down_sample(args.max_points / n_down)
                print(f'[INFO] 랜덤 샘플링 후: {len(pcd_down.points):,} 포인트')
            # 너무 적으면 Voxel 크기 줄여서 재시도
            elif n_down < 10000:
                print(f'[WARN] 포인트가 너무 적음({n_down}). Voxel 크기를 줄여 재시도...')
                voxel_size = voxel_size * 0.1
                print(f'[INFO] 새 Voxel 크기: {voxel_size:.6f}')
                pcd_down = pcd.voxel_down_sample(voxel_size=voxel_size)
                n_down = len(pcd_down.points)
                print(f'[INFO] 재시도 후: {n_down:,} 포인트')
                if n_down > args.max_points:
                    pcd_down = pcd_down.random_down_sample(args.max_points / n_down)
                    print(f'[INFO] 랜덤 샘플링 후: {len(pcd_down.points):,} 포인트')
            pcd = pcd_down
        else:
            print(f'[INFO] 다운샘플링 불필요 ({n_orig:,} ≤ {args.max_points:,})')

        n_final = len(pcd.points)
        print(f'[INFO] 최종 포인트 수: {n_final:,}')

        if n_final < 100:
            print('[ERROR] 포인트가 너무 적습니다. --voxel_size 옵션으로 직접 지정하세요.')
            print('  예: python3 scripts/06_make_mesh.py --data_dir output --voxel_size 0.01')
            sys.exit(1)

        print(f'[3/5] 법선 벡터 추정...')
        pts_arr = np.asarray(pcd.points)
        bbox_sz = pts_arr.max(axis=0) - pts_arr.min(axis=0)
        radius = float(bbox_sz.max()) * 0.02  # bbox의 2%
        radius = max(0.01, radius)
        pcd.estimate_normals(
            search_param=o3d.geometry.KDTreeSearchParamHybrid(radius=radius, max_nn=30)
        )
        pcd.orient_normals_consistent_tangent_plane(100)
        print(f'[INFO] 법선 추정 완료 (radius={radius:.4f})')

        print(f'[4/5] Poisson Meshing (depth={args.depth})...')
        mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
            pcd, depth=args.depth, width=0, scale=1.1, linear_fit=False
        )

        # 밀도가 낮은 삼각형 제거 (노이즈 제거)
        densities_arr = np.asarray(densities)
        density_threshold = np.percentile(densities_arr, 5)
        vertices_to_remove = densities_arr < density_threshold
        mesh.remove_vertices_by_mask(vertices_to_remove)
        mesh.remove_degenerate_triangles()
        mesh.remove_duplicated_triangles()

        n_v = len(mesh.vertices)
        n_f = len(mesh.triangles)
        print(f'[INFO] 메시: {n_v:,} 정점, {n_f:,} 삼각형')

        if n_v < 100:
            print('[WARN] 메시가 너무 작습니다. depth를 낮추거나 voxel_size를 조정하세요.')

        o3d.io.write_triangle_mesh(mesh_path, mesh)
        print(f'[OK] 메시 저장: {mesh_path}')

        # 웹 뷰어용 포인트 클라우드 JSON 생성
        print(f'[5/5] 웹 뷰어용 JSON 생성...')
        pts_web = np.asarray(pcd.points)
        clrs_web = np.asarray(pcd.colors) if pcd.has_colors() else None
        step = max(1, len(pts_web) // args.web_points)
        web_pts = pts_web[::step].tolist()
        web_clrs = (clrs_web[::step].tolist() if clrs_web is not None
                    else [[0.5, 0.7, 0.9]] * len(web_pts))
        with open(web_json_path, 'w') as f:
            json.dump({'points': web_pts, 'colors': web_clrs,
                       'scale_factor': scale_factor}, f)
        print(f'[OK] 웹 JSON: {web_json_path} ({len(web_pts):,} 포인트)')

    except ImportError as e:
        print(f'[ERROR] Open3D 로드 실패: {e}')
        print('[INFO] numpy 기반 다운샘플링 후 COLMAP Poisson 재시도')

        # numpy로 직접 PLY 읽기
        print(f'[1/3] PLY 로드 및 다운샘플링 중...')
        with open(ply_path, 'rb') as f:
            header_lines = []
            while True:
                line = f.readline().decode('utf-8', errors='ignore').strip()
                header_lines.append(line)
                if line == 'end_header':
                    break
            header = '\n'.join(header_lines)
            n_vertex = int([l for l in header_lines if 'element vertex' in l][0].split()[-1])
            has_color = 'red' in header
            props = []
            for l in header_lines:
                if l.startswith('property'):
                    parts = l.split()
                    props.append((parts[1], parts[2]))
            type_map = {'float':'f','float32':'f','double':'d','float64':'d',
                        'uchar':'B','uint8':'B','int':'i','int32':'i'}
            fmt = '<' + ''.join(type_map.get(t, 'f') for t, n in props)
            sz = struct.calcsize(fmt)
            prop_names = [n for t, n in props]

            step = max(1, n_vertex // args.max_points)
            points, colors = [], []
            for i in range(n_vertex):
                data = f.read(sz)
                if len(data) < sz: break
                vals = struct.unpack(fmt, data)
                row = dict(zip(prop_names, vals))
                if i % step == 0:
                    points.append([row.get('x',0), row.get('y',0), row.get('z',0)])
                    r = row.get('red', row.get('diffuse_red', 128))
                    g = row.get('green', row.get('diffuse_green', 128))
                    b = row.get('blue', row.get('diffuse_blue', 128))
                    colors.append([r/255.0, g/255.0, b/255.0])

        points = np.array(points)
        colors = np.array(colors)
        print(f'[INFO] 로드: {len(points):,} 포인트')

        # 다운샘플링된 PLY 저장
        ds_ply = os.path.join(args.data_dir, 'colmap_dense', 'dense', 'fused_downsampled.ply')
        n = len(points)
        with open(ds_ply, 'wb') as f:
            header = (f"ply\nformat binary_little_endian 1.0\n"
                      f"element vertex {n}\n"
                      f"property float x\nproperty float y\nproperty float z\n"
                      f"property uchar red\nproperty uchar green\nproperty uchar blue\n"
                      f"end_header\n")
            f.write(header.encode())
            for i in range(n):
                p, c = points[i], colors[i]
                f.write(struct.pack('<fff', p[0], p[1], p[2]))
                f.write(struct.pack('BBB', int(c[0]*255), int(c[1]*255), int(c[2]*255)))
        print(f'[OK] 다운샘플링 PLY: {ds_ply} ({n:,} 포인트)')

        import subprocess
        result = subprocess.run([
            'colmap', 'poisson_mesher',
            '--input_path', ds_ply,
            '--output_path', mesh_path
        ], capture_output=True, text=True)
        if result.returncode == 0:
            print(f'[OK] COLMAP Poisson 완료: {mesh_path}')
        else:
            print(f'[ERROR] COLMAP Poisson 실패:\n{result.stderr[-500:]}')

        step2 = max(1, n // args.web_points)
        web_pts = points[::step2].tolist()
        web_clrs = colors[::step2].tolist()
        with open(web_json_path, 'w') as f:
            json.dump({'points': web_pts, 'colors': web_clrs}, f)
        print(f'[OK] 웹 JSON: {web_json_path} ({len(web_pts):,} 포인트)')

    print('\n[완료] 다음 단계:')
    print(f'  cd {args.data_dir} && python3 -m http.server 8080')
    print(f'  브라우저: http://localhost:8080/web/')

if __name__ == '__main__':
    main()
