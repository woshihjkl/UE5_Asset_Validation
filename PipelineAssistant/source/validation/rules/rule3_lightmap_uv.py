import unreal
import sys
import os

_current_file = os.path.abspath(__file__)
_source_dir = os.path.dirname(os.path.dirname(os.path.dirname(_current_file)))
if _source_dir not in sys.path:
    sys.path.insert(0, _source_dir)

from utils import normalize_folder_path


def get_lightmap_uv_config(config):
    """从传入的配置字典读取LightmapUV设置"""
    return config.get("LightmapUV", {})


def _check_single_lightmap_uv(mesh, asset_name, asset_path, config):
    """
    检测单个StaticMesh的Lightmap UV（核心逻辑提取）

    【业务层】
    Lightmap UV缺失导致光照烘焙出现黑斑、漏光、脏块，
    美术需要反复返工烘焙。这是项目中最常见的烘焙返工原因。

    【标准层】
    第二套UV（Channel 1）必须存在。
    第二套UV必须在0-1内（当前版本无法检测，见引擎层说明）。
    第二套UV必须无重叠（当前版本无法检测，已明确砍掉）。

    【引擎层】
    UE 5.7.4 Python API：
    - get_num_uv_channels(mesh, lod_index) 可用：获取UV通道数量
    - 无法获取逐顶点UV坐标（render_data/sections属性不存在Python绑定）
    - 无法做UV Island重叠检测（需要Flood Fill/Union Find几何算法）

    当前实现：检测UV通道数量是否>=2（即是否存在Channel 1作为Lightmap UV）

    【边界层】
    - 程序化植被、地形模型、Nanite网格可跳过Lightmap UV检测
    - 支持白名单配置
    - 面试时坦诚说明："当前版本受限于Python API，精确的0-1范围检测和
      Island重叠检测需要C++插件扩展，已规划为后续优化"

    【延伸层】
    - 接入UE内置Lightmap UV自动生成（Generate Lightmap UVs）
    - 使用EditorStaticMeshLibrary.generate_box_uv_channel等工具自动修复
    - C++插件扩展实现精确的UV几何分析
    """
    violations = []

    require_channel2 = config.get("RequireChannel2", True)

    if not require_channel2:
        return []

    try:
        uv_channel_count = unreal.EditorStaticMeshLibrary.get_num_uv_channels(mesh, 0)
    except Exception as e:
        unreal.log_warning(f"[WARNING] [Rule3] Failed to get UV channels for {asset_path}: {e}")
        return []

    if uv_channel_count < 2:
        violations.append({
            "asset_path": asset_path,
            "asset_name": asset_name,
            "asset_class": "StaticMesh",
            "rule": "LightmapUV_MissingChannel2",
            "severity": "Error",
            "current_value": f"{uv_channel_count} UV channel(s)",
            "threshold": "At least 2 UV channels (Channel 0 for texture, Channel 1 for lightmap)",
            "message": f"Only {uv_channel_count} UV channel(s) found, Lightmap UV (Channel 1) is missing",
            "suggestion": "Add a second UV channel for Lightmap baking. In UE: StaticMesh Editor -> UV Settings -> Generate Lightmap UVs. In DCC: Export FBX with Channel 2 as Lightmap UV (must be in 0-1 space, no overlapping islands). Without Lightmap UV, baked lighting will show black spots, light leaks, and dirty artifacts."
        })
    else:
        unreal.log(f"[INFO] [Rule3] {asset_name}: {uv_channel_count} UV channels found. "
                  f"0-1 range and overlap check skipped (Python API limitation, requires C++ extension).")

    return violations


def check_lightmap_uv(folder_path="/Game", config=None):
    """
    规则3：Lightmap UV合规性检测（Plan B降级版）

    扫描文件夹下的所有StaticMesh的Lightmap UV。

    【配置注入】
    config参数由pipeline统一传入，保证同轮扫描使用同一套配置。
    如果独立调用（如单规则测试），config为None时回退读取JSON。
    """
    folder_path = normalize_folder_path(folder_path)

    # 独立调用时回退读取配置
    if config is None:
        from validation.core.config_loader import get_config
        config = get_config()

    lightmap_config = get_lightmap_uv_config(config)

    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    filter = unreal.ARFilter(package_paths=[folder_path], recursive_paths=True)
    asset_data_list = registry.get_assets(filter)

    if not asset_data_list:
        unreal.log("[INFO] [Rule3] No assets found in specified folder.")
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
            unreal.log_warning(f"[WARNING] [Rule3] Failed to load asset {path}: {e}")
            continue

        asset_name = str(asset_data.asset_name)
        v = _check_single_lightmap_uv(mesh, asset_name, path, lightmap_config)
        violations.extend(v)

    unreal.log(f"[OK] [Rule3] Checked {checked_count} StaticMeshes, found {len(violations)} violations.")
    return violations


def check_lightmap_uv_on_selected(selected_assets=None, config=None):
    """
    规则3：扫描选中的资产（内容浏览器选中）

    【配置注入】
    config参数由pipeline统一传入，保证同轮扫描使用同一套配置。
    """
    if selected_assets is None:
        selected_assets = unreal.EditorUtilityLibrary.get_selected_assets()

    if not selected_assets:
        unreal.log_warning("[WARNING] [Rule3] No assets selected.")
        return []

    # 独立调用时回退读取配置
    if config is None:
        from validation.core.config_loader import get_config
        config = get_config()

    lightmap_config = get_lightmap_uv_config(config)
    violations = []
    checked_count = 0

    for asset in selected_assets:
        asset_class = asset.get_class().get_name()
        if asset_class != "StaticMesh":
            continue

        checked_count += 1
        asset_name = asset.get_name()
        asset_path = asset.get_path_name()

        v = _check_single_lightmap_uv(asset, asset_name, asset_path, lightmap_config)
        violations.extend(v)

    unreal.log(f"[OK] [Rule3] Checked {checked_count} selected StaticMeshes, found {len(violations)} violations.")
    return violations


def print_violations(violations):
    """格式化输出违规结果"""
    if not violations:
        unreal.log("[OK] [Rule3] All StaticMeshes passed Lightmap UV validation.")
        return

    unreal.log_warning(f"[WARNING] [Rule3] Found {len(violations)} violations:")
    for v in violations:
        severity = v.get("severity", "Warning")
        msg = f"[{severity}] {v['asset_name']} | {v['rule']}: {v['message']}"
        if severity == "Error":
            unreal.log_error(msg)
        else:
            unreal.log_warning(msg)
        unreal.log(f"   -> Fix: {v['suggestion']}")


def run_rule3(folder_path="/Game"):
    """一键执行规则3"""
    violations = check_lightmap_uv(folder_path)
    print_violations(violations)
    return violations


def run_rule3_on_selected():
    """一键执行规则3（选中资产）"""
    violations = check_lightmap_uv_on_selected()
    print_violations(violations)
    return violations