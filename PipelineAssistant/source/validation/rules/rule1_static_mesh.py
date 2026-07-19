import unreal
import sys
import os

_current_file = os.path.abspath(__file__)
_source_dir = os.path.dirname(os.path.dirname(os.path.dirname(_current_file)))
if _source_dir not in sys.path:
    sys.path.insert(0, _source_dir)

from utils import normalize_folder_path, is_path_exempt


def get_mesh_thresholds(config):
    """从传入的配置字典读取StaticMesh阈值"""
    return config.get("StaticMesh", {})


def get_lod_exempt_paths(config):
    """从传入的配置字典读取LOD豁免路径"""
    mesh_config = get_mesh_thresholds(config)
    return mesh_config.get("LODExemptPaths", [])


def _check_single_static_mesh(mesh, asset_name, asset_path, threshold, lod_exempt_paths):
    """
    检测单个StaticMesh的核心逻辑（提取出来复用）

    【业务层】
    面数超标直接增加GPU顶点计算压力，拉高DrawCall成本。
    大世界场景无LOD会导致远距离仍渲染高精度模型，帧率暴跌。

    【标准层】
    角色<=5万Tri/场景道具<=2万Tri/植被视项目而定
    LOD至少2级（LOD0为最高精度，作为规范基准）
    同时检测Triangles和Vertex Count（见引擎层原理）

    【引擎层】
    UE 5.7.4 Python API：
    - get_num_lods()：获取LOD层级总数
    - get_num_triangles(lod_index)：获取指定LOD的三角形数量
    - get_num_vertices(lod_index)：获取指定LOD的顶点数量

    关键原理：Triangles是建模概念，Vertices才是GPU实际处理量。
    硬边、UV切缝、法线拆分会导致Vertex Split——同一个几何位置的顶点
    在GPU中被拆分为多个（因为需要不同的法线/UV/切线数据）。
    所以一个1万Tri的模型，如果全是硬边，Vertex Count可能飙到3-4万。
    只检测Triangles的人，不懂渲染管线。

    【边界层】
    - 过滤__External垃圾数据（UE5 World Partition生成）
    - 跳过None资产（get_asset()可能返回None）
    - 只处理StaticMesh类资产
    - 原型资产路径白名单豁免LOD检测（开发中资产不强制LOD）
    - 后续扩展：Nanite网格白名单、程序化资产生成豁免

    【延伸层】
    - 接入自动LOD生成（UE内置Simplygon/ProxyLOD）
    - 面数超标自动邮件通知美术
    - 按Camera距离自动计算LOD切换阈值
    """
    violations = []

    is_lod_exempt = is_path_exempt(asset_path, lod_exempt_paths)

    lod_count = mesh.get_num_lods()
    tri_count = mesh.get_num_triangles(0)
    vert_count = mesh.get_num_vertices(0)

    # ========== 检测1：Triangles ==========
    if tri_count > threshold["MaxTriangles"]:
        violations.append({
            "asset_path": asset_path,
            "asset_name": asset_name,
            "asset_class": "StaticMesh",
            "rule": "StaticMesh_TriangleCount",
            "severity": "Error",
            "current_value": tri_count,
            "threshold": threshold["MaxTriangles"],
            "message": f"LOD0 Triangle Count {tri_count} exceeds threshold {threshold['MaxTriangles']}",
            "suggestion": "Reduce triangle count in DCC tool, or enable Nanite for high-poly static meshes. Consider automatic LOD generation via Simplygon."
        })

    # ========== 检测2：Vertex Count（面试核心区分点） ==========
    if vert_count > threshold["MaxVertices"]:
        violations.append({
            "asset_path": asset_path,
            "asset_name": asset_name,
            "asset_class": "StaticMesh",
            "rule": "StaticMesh_VertexCount",
            "severity": "Error",
            "current_value": vert_count,
            "threshold": threshold["MaxVertices"],
            "message": f"LOD0 Vertex Count {vert_count} exceeds threshold {threshold['MaxVertices']} (Triangle Count: {tri_count})",
            "suggestion": "Check for excessive hard edges, UV seams, or split normals causing vertex splits. GPU processes vertices, not triangles. A 10k Tri mesh with all hard edges can have 30k+ vertices. Optimize smoothing groups and UV layout."
        })

    # ========== 检测3：LOD层级 ==========
    if is_lod_exempt:
        if lod_count < threshold["MinLODCount"]:
            unreal.log(f"[INFO] [Rule1] {asset_name}: LOD count {lod_count} below standard "
                      f"(min {threshold['MinLODCount']}), but asset is in exempt path "
                      f"(prototype/WIP). Skipping LOD check.")
    else:
        if lod_count < threshold["MinLODCount"]:
            violations.append({
                "asset_path": asset_path,
                "asset_name": asset_name,
                "asset_class": "StaticMesh",
                "rule": "StaticMesh_LOD",
                "severity": "Warning",
                "current_value": lod_count,
                "threshold": threshold["MinLODCount"],
                "message": f"LOD count {lod_count} below minimum {threshold['MinLODCount']} (only LOD0 exists)",
                "suggestion": "Add LODs using UE built-in Simplygon or manual LOD chains. Without LODs, distant objects render at full resolution, killing frame rate in open worlds."
            })

    return violations


def check_static_mesh_performance(folder_path="/Game", asset_category="Prop", config=None):
    """
    规则1：扫描文件夹下的所有StaticMesh

    【配置注入】
    config参数由pipeline统一传入，保证同轮扫描使用同一套配置。
    如果独立调用（如单规则测试），config为None时回退读取JSON。
    """
    folder_path = normalize_folder_path(folder_path)

    # 独立调用时回退读取配置
    if config is None:
        from validation.core.config_loader import get_config
        config = get_config()

    mesh_config = get_mesh_thresholds(config)
    threshold = mesh_config.get(asset_category, mesh_config.get("Prop", {
        "MaxTriangles": 20000, "MaxVertices": 40000, "MinLODCount": 2
    }))
    lod_exempt_paths = get_lod_exempt_paths(config)

    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    filter = unreal.ARFilter(
        package_paths=[folder_path],
        recursive_paths=True
    )
    asset_data_list = registry.get_assets(filter)

    if not asset_data_list:
        unreal.log("[INFO] [Rule1] No assets found in specified folder.")
        return []

    violations = []
    checked_count = 0

    for asset_data in asset_data_list:
        path = str(asset_data.package_name)
        if "__External" in path:
            continue

        asset_class = str(asset_data.asset_class_path.asset_name) if asset_data.asset_class_path else "None"
        if asset_class != "StaticMesh":
            continue

        checked_count += 1

        try:
            asset = asset_data.get_asset()
            if asset is None:
                continue
            mesh = unreal.StaticMesh.cast(asset)
            if mesh is None:
                continue
        except Exception as e:
            unreal.log_warning(f"[WARNING] [Rule1] Failed to load asset {path}: {e}")
            continue

        asset_name = str(asset_data.asset_name)
        v = _check_single_static_mesh(mesh, asset_name, path, threshold, lod_exempt_paths)
        violations.extend(v)

    unreal.log(f"[OK] [Rule1] Checked {checked_count} StaticMeshes, found {len(violations)} violations.")
    return violations


def check_static_mesh_performance_on_selected(selected_assets=None, asset_category="Prop", config=None):
    """
    规则1：扫描选中的资产（内容浏览器选中）

    【配置注入】
    config参数由pipeline统一传入，保证同轮扫描使用同一套配置。
    """
    if selected_assets is None:
        selected_assets = unreal.EditorUtilityLibrary.get_selected_assets()

    if not selected_assets:
        unreal.log_warning("[WARNING] [Rule1] No assets selected.")
        return []

    # 独立调用时回退读取配置
    if config is None:
        from validation.core.config_loader import get_config
        config = get_config()

    mesh_config = get_mesh_thresholds(config)
    threshold = mesh_config.get(asset_category, mesh_config.get("Prop", {
        "MaxTriangles": 20000, "MaxVertices": 40000, "MinLODCount": 2
    }))
    lod_exempt_paths = get_lod_exempt_paths(config)

    violations = []
    checked_count = 0

    for asset in selected_assets:
        asset_class = asset.get_class().get_name()
        if asset_class != "StaticMesh":
            continue

        checked_count += 1
        asset_name = asset.get_name()
        asset_path = asset.get_path_name()

        v = _check_single_static_mesh(asset, asset_name, asset_path, threshold, lod_exempt_paths)
        violations.extend(v)

    unreal.log(f"[OK] [Rule1] Checked {checked_count} selected StaticMeshes, found {len(violations)} violations.")
    return violations


def print_violations(violations):
    """格式化输出违规结果到UE日志控制台"""
    if not violations:
        unreal.log("[OK] [Rule1] All StaticMeshes passed performance validation.")
        return

    unreal.log_warning(f"[WARNING] [Rule1] Found {len(violations)} violations:")
    for v in violations:
        severity = v.get("severity", "Warning")
        msg = f"[{severity}] {v['asset_name']} | {v['rule']}: {v['message']}"
        if severity == "Error":
            unreal.log_error(msg)
        else:
            unreal.log_warning(msg)
        unreal.log(f"   -> Fix: {v['suggestion']}")


def run_rule1(folder_path="/Game", asset_category="Prop"):
    """一键执行规则1并输出结果"""
    violations = check_static_mesh_performance(folder_path, asset_category)
    print_violations(violations)
    return violations


def run_rule1_on_selected(asset_category="Prop"):
    """一键执行规则1（选中资产）"""
    violations = check_static_mesh_performance_on_selected(asset_category=asset_category)
    print_violations(violations)
    return violations