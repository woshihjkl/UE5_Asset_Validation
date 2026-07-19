import unreal
import sys
import os

_current_file = os.path.abspath(__file__)
_source_dir = os.path.dirname(os.path.dirname(os.path.dirname(_current_file)))
if _source_dir not in sys.path:
    sys.path.insert(0, _source_dir)

from utils import normalize_asset_path, normalize_folder_path, is_path_exempt


# 边界层：递归深度限制，防止循环引用导致死循环
MAX_RECURSION_DEPTH = 10


def get_hard_reference_config(config):
    """从传入的配置字典读取HardReference设置"""
    return config.get("HardReference", {})


def get_exempt_paths(config):
    """从传入的配置字典获取豁免路径"""
    hard_ref_config = get_hard_reference_config(config)
    return hard_ref_config.get("ExemptPaths", ["/Game/WIP", "/Game/Temp", "/Game/Test"])


def get_max_recursion_depth(config):
    """从传入的配置字典获取最大递归深度"""
    hard_ref_config = get_hard_reference_config(config)
    return hard_ref_config.get("MaxRecursionDepth", 10)


def get_hard_dependencies_recursive(asset_path, config, visited=None, depth=0):
    """
    递归获取资产的Hard Reference依赖链

    【业务层】
    材质丢失贴图引用、依赖链断裂会导致打包失败、资源缺失崩溃、版本控制冲突。
    需要在导入阶段就发现，而不是等打包时才报错。

    【标准层】
    所有Hard Reference必须指向有效资产。
    不允许存在空引用、已删除资产的残留引用。

    【引擎层】
    AssetRegistry.get_dependencies() 获取直接Hard依赖。
    对每个依赖继续递归，构建完整引用树。
    get_asset_by_object_path() 验证资产是否存在。

    【边界层】
    - visited集合去重，防止循环引用死循环
    - 最大深度限制（默认10层，JSON可配置）
    - 过滤引擎内部资源(/Engine/、/Script/)
    - 过滤__External垃圾数据
    - 只检测Hard Reference，不检测Soft Reference（面试知识储备）

    【延伸层】
    - Soft Reference分析（运行时异步加载监控）
    - 引用链可视化（资产依赖图谱）
    - 自动修复建议（替换缺失引用为默认材质/贴图）

    Args:
        asset_path: 资产路径
        config: 配置字典（由pipeline统一传入）
        visited: 已访问路径集合（递归用）
        depth: 当前递归深度

    Returns:
        list: 所有依赖资产列表，每个元素包含name, path, class, is_valid
    """
    if visited is None:
        visited = set()

    normalized_path = normalize_asset_path(asset_path)
    if not normalized_path:
        return []

    max_depth = get_max_recursion_depth(config)
    if normalized_path in visited or depth > max_depth:
        return []

    visited.add(normalized_path)

    registry = unreal.AssetRegistryHelpers.get_asset_registry()

    asset_data = registry.get_asset_by_object_path(normalized_path)
    if not asset_data.is_valid():
        return []

    package_name = unreal.Name(str(asset_data.package_name))
    dependency_options = unreal.AssetRegistryDependencyOptions(
        include_hard_package_references=True,
        include_soft_package_references=False,
        include_searchable_names=False,
        include_soft_management_references=False,
        include_hard_management_references=False
    )

    try:
        dependency_names = registry.get_dependencies(package_name, dependency_options)
    except Exception as e:
        return []

    if dependency_names is None:
        return []

    result = []

    for dep_name in dependency_names:
        dep_path_str = str(dep_name)

        if dep_path_str.startswith("/Engine/") or dep_path_str.startswith("/Script/"):
            continue
        if "__External" in dep_path_str:
            continue

        dep_asset_name = dep_path_str.split("/")[-1]
        full_object_path = f"{dep_path_str}.{dep_asset_name}"

        dep_data = registry.get_asset_by_object_path(full_object_path)
        is_valid = dep_data.is_valid()

        dep_class = "Unknown"
        if is_valid:
            class_path = dep_data.asset_class_path
            dep_class = str(class_path.asset_name) if hasattr(class_path, 'asset_name') else str(class_path)

        dep_info = {
            "name": dep_asset_name,
            "path": dep_path_str,
            "class": dep_class,
            "is_valid": is_valid,
            "parent_path": normalized_path,
            "depth": depth
        }

        result.append(dep_info)

        if is_valid:
            children = get_hard_dependencies_recursive(full_object_path, config, visited, depth + 1)
            result.extend(children)

    return result


def _check_single_hard_reference(asset, asset_name, asset_path, exempt_paths, config):
    """
    检测单个资产的Hard Reference完整性（核心逻辑提取）

    【配置注入】
    config参数由pipeline统一传入，保证同轮扫描使用同一套配置。
    """
    violations = []

    is_exempt = is_path_exempt(asset_path, exempt_paths)
    if is_exempt:
        return []

    asset_class = asset.get_class().get_name()
    if asset_class not in ["StaticMesh", "Material", "MaterialInstanceConstant"]:
        return []

    full_object_path = f"{asset_path}.{asset_name}"
    dependencies = get_hard_dependencies_recursive(full_object_path, config)

    unreal.log(f"[DEBUG] Asset: {asset_name}")
    unreal.log(f"[DEBUG] Dependency Count: {len(dependencies)}")

    for dep in dependencies:
        unreal.log(
        f"[DEBUG] {dep['path']}  valid={dep['is_valid']}"
        )
        
    for dep in dependencies:
        if not dep["is_valid"]:
            violations.append({
                "asset_path": asset_path,
                "asset_name": asset_name,
                "asset_class": asset_class,
                "rule": "HardReference_Missing",
                "severity": "Error",
                "current_value": f"Missing: {dep['path']}",
                "threshold": "All Hard References must be valid",
                "message": f"Hard Reference to '{dep['name']}' ({dep['path']}) is missing or invalid",
                "suggestion": f"Fix the broken reference in {asset_name}, or remove the unused reference. Broken Hard References cause packaging failures and runtime crashes. Check if the referenced asset was deleted or moved."
            })

    return violations


def check_hard_reference_integrity(folder_path="/Game", config=None):
    """
    规则4：资产引用完整性检测（Hard Reference）

    【业务层】
    材质丢失贴图引用、依赖链断裂会导致打包失败、资源缺失崩溃、版本控制冲突。
    这是项目中最常见的打包阻塞原因。

    【标准层】
    所有Hard Reference必须指向有效资产。
    不允许存在空引用、已删除资产的残留引用。

    【引擎层】
    AssetRegistry.get_dependencies() 获取资产依赖列表。
    get_asset_by_object_path() 验证资产是否存在。
    递归遍历构建完整引用链。

    【边界层】
    - 只检测Hard Reference，不做Soft Reference检测（面试知识储备）
    - Soft Reference是异步加载，在导入阶段不一定能发现
    - Hard Reference缺失会导致打包直接报错，必须拦截
    - 允许配置例外路径（WIP文件夹、测试资源）
    - 最大递归深度限制，防止循环引用

    【延伸层】
    - Soft Reference分析（运行时异步加载监控）
    - 引用链可视化（资产依赖图谱）
    - 自动修复建议（替换缺失引用为默认材质/贴图）

    【配置注入】
    config参数由pipeline统一传入，保证同轮扫描使用同一套配置。
    如果独立调用（如单规则测试），config为None时回退读取JSON。

    Args:
        folder_path: 扫描目录
        config: 配置字典（由pipeline统一传入）

    Returns:
        list: 违规列表（缺失引用）
    """
    folder_path = normalize_folder_path(folder_path)

    # 独立调用时回退读取配置
    if config is None:
        from validation.core.config_loader import get_config
        config = get_config()

    exempt_paths = get_exempt_paths(config)

    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    filter = unreal.ARFilter(
        package_paths=[folder_path],
        recursive_paths=True
    )
    asset_data_list = registry.get_assets(filter)

    if not asset_data_list:
        unreal.log("[INFO] [Rule4] No assets found in specified folder.")
        return []

    violations = []
    checked_count = 0

    for asset_data in asset_data_list:
        path = str(asset_data.package_name)

        if "__External" in path:
            continue

        asset_class = str(asset_data.asset_class_path.asset_name) if asset_data.asset_class_path else "None"
        if asset_class not in ["StaticMesh", "Material", "MaterialInstanceConstant"]:
            continue

        checked_count += 1

        try:
            asset = asset_data.get_asset()
            if asset is None:
                continue
        except Exception as e:
            unreal.log_warning(f"[WARNING] [Rule4] Failed to load asset {path}: {e}")
            continue

        asset_name = str(asset_data.asset_name)
        v = _check_single_hard_reference(asset, asset_name, path, exempt_paths, config)
        violations.extend(v)

    unreal.log(f"[OK] [Rule4] Checked {checked_count} assets, found {len(violations)} missing references.")
    return violations


def check_hard_reference_on_selected(selected_assets=None, config=None):
    """
    规则4：扫描选中的资产（内容浏览器选中）

    【配置注入】
    config参数由pipeline统一传入，保证同轮扫描使用同一套配置。
    """
    if selected_assets is None:
        selected_assets = unreal.EditorUtilityLibrary.get_selected_assets()

    if not selected_assets:
        unreal.log_warning("[WARNING] [Rule4] No assets selected.")
        return []

    # 独立调用时回退读取配置
    if config is None:
        from validation.core.config_loader import get_config
        config = get_config()

    exempt_paths = get_exempt_paths(config)
    violations = []
    checked_count = 0

    for asset in selected_assets:
        asset_class = asset.get_class().get_name()
        if asset_class not in ["StaticMesh", "Material", "MaterialInstanceConstant"]:
            continue

        checked_count += 1
        asset_name = asset.get_name()
        asset_path = asset.get_path_name()

        v = _check_single_hard_reference(asset, asset_name, asset_path, exempt_paths, config)
        violations.extend(v)

    unreal.log(f"[OK] [Rule4] Checked {checked_count} selected assets, found {len(violations)} missing references.")
    return violations


def print_violations(violations):
    """格式化输出违规结果"""
    if not violations:
        unreal.log("[OK] [Rule4] All Hard References are valid.")
        return

    unreal.log_warning(f"[WARNING] [Rule4] Found {len(violations)} broken references:")
    for v in violations:
        severity = v.get("severity", "Warning")
        msg = f"[{severity}] {v['asset_name']} | {v['rule']}: {v['message']}"
        if severity == "Error":
            unreal.log_error(msg)
        else:
            unreal.log_warning(msg)
        unreal.log(f"   -> Fix: {v['suggestion']}")


def run_rule4(folder_path="/Game"):
    """一键执行规则4"""
    violations = check_hard_reference_integrity(folder_path)
    print_violations(violations)
    return violations


def run_rule4_on_selected():
    """一键执行规则4（选中资产）"""
    violations = check_hard_reference_on_selected()
    print_violations(violations)
    return violations