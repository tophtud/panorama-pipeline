#!/usr/bin/env python3
"""
포인트클라우드(pointcloud.ply)에서 3D 메쉬 생성
Open3D Poisson Surface Reconstruction 사용
"""
import numpy as np
import sys
import os

# numpy 버전 호환성
try:
    import open3d as o3d
    print(f"[OK] Open3D {o3d.__version__} 로드 완료")
except ImportError:
    print("[ERROR] Open3D 없음. 설치: pip install open3d")
    sys.exit(1)

INPUT_PLY = "/home/ubuntu/panorama_pipeline/output/pointcloud.ply"
OUTPUT_MESH = "/home/ubuntu/panorama_pipeline/output/mesh/scene_mesh.ply"

print(f"[INFO] 포인트클라우드 로드: {INPUT_PLY}")
pcd = o3d.io.read_point_cloud(INPUT_PLY)
print(f"[INFO] 포인트 수: {len(pcd.points)}")

# 법선 추정
print("[INFO] 법선 추정 중...")
pcd.estimate_normals(
    search_param=o3d.geometry.KDTreeSearchParamHybrid(radius=0.3, max_nn=30)
)
pcd.orient_normals_consistent_tangent_plane(k=15)

# 이상치 제거
print("[INFO] 이상치 제거 중...")
pcd_clean, ind = pcd.remove_statistical_outlier(nb_neighbors=20, std_ratio=2.0)
print(f"[INFO] 정리 후 포인트 수: {len(pcd_clean.points)}")

# Poisson 메쉬 생성
print("[INFO] Poisson 메쉬 생성 중...")
mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
    pcd_clean, depth=9, width=0, scale=1.1, linear_fit=False
)
print(f"[INFO] 초기 메쉬: {len(mesh.vertices)} 정점, {len(mesh.triangles)} 삼각형")

# 밀도 기반 저밀도 삼각형 제거
densities = np.asarray(densities)
density_threshold = np.percentile(densities, 15)
vertices_to_remove = densities < density_threshold
mesh.remove_vertices_by_mask(vertices_to_remove)
print(f"[INFO] 정리 후 메쉬: {len(mesh.vertices)} 정점, {len(mesh.triangles)} 삼각형")

# 법선 계산
mesh.compute_vertex_normals()

# 색상 추가 (포인트클라우드에서 보간)
if pcd_clean.has_colors():
    print("[INFO] 색상 전달 중...")
    # 각 메쉬 정점에 가장 가까운 포인트 색상 할당
    pcd_tree = o3d.geometry.KDTreeFlann(pcd_clean)
    mesh_colors = []
    for v in mesh.vertices:
        [_, idx, _] = pcd_tree.search_knn_vector_3d(v, 1)
        mesh_colors.append(pcd_clean.colors[idx[0]])
    mesh.vertex_colors = o3d.utility.Vector3dVector(np.array(mesh_colors))

# 저장
print(f"[INFO] 메쉬 저장: {OUTPUT_MESH}")
o3d.io.write_triangle_mesh(OUTPUT_MESH, mesh, write_ascii=False)
print(f"[OK] 완료! 파일 크기: {os.path.getsize(OUTPUT_MESH) / 1024 / 1024:.1f} MB")
print(f"[OK] 정점: {len(mesh.vertices)}, 삼각형: {len(mesh.triangles)}")
