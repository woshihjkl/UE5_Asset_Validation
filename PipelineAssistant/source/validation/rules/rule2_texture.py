import unreal
import sys
import os

_current_file = os.path.abspath(__file__)
_source_dir = os.path.dirname(os.path.dirname(os.path.dirname(_current_file)))
if _source_dir not in sys.path:
    sys.path.insert(0, _source_dir)

from utils import normalize_folder_path, is_path_exempt


def is_power_of_two(n):
    return n > 0 and (n & (n - 1)) == 0


def get_texture_config(config):
    """从传入的配置字典读取Texture设置"""
    return config.get("Texture", {})


def get_texture_exempt_paths(config):
    """从传入的配置字典读取Texture豁免路径"""
    texture_config = get_texture_config(config)
    return texture_config.get("ExemptPaths", ["/Game/UI", "/Game/HUD", "/Game/Widget", "/Game/Icons"])


def _check_single_texture(tex, asset_name, asset_path, threshold, exempt_paths):
    """
    检测单个Texture2D的核心逻辑（提取出来复用）
    """
    violations = []

    size_x = tex.blueprint_get_size_x()
    size_y = tex.blueprint_get_size_y()
    compression = tex.compression_settings

    is_ui_texture = is_path_exempt(asset_path, exempt_paths)

    require_power_of_two = threshold.get("RequirePowerOfTwo", True)
    max_size = threshold.get("MaxSize", 2048)

    if not is_ui_texture and require_power_of_two:
        if not is_power_of_two(size_x) or not is_power_of_two(size_y):
            violations.append({
                "asset_path": asset_path,
                "asset_name": asset_name,
                "asset_class": "Texture2D",
                "rule": "Texture_PowerOfTwo",
                "severity": "Error",
                "current_value": f"{size_x}x{size_y}",
                "threshold": "Power of 2 (256/512/1024/2048/4096)",
                "message": f"Texture size {size_x}x{size_y} is not power of 2",
                "suggestion": "Resize to power of 2 (e.g., 1024x1024 or 2048x2048). Non-power-of-2 textures cannot generate full Mipmap chain, causing blurry distant sampling and VRAM waste. Some mobile GPUs don't support NPOT at all."
            })

    max_size_actual = max(size_x, size_y)
    if max_size_actual > max_size:
        violations.append({
            "asset_path": asset_path,
            "asset_name": asset_name,
            "asset_class": "Texture2D",
            "rule": "Texture_MaxSize",
            "severity": "Warning",
            "current_value": f"{size_x}x{size_y}",
            "threshold": f"Max {max_size}",
            "message": f"Texture size {size_x}x{size_y} exceeds project max {max_size}",
            "suggestion": f"Consider downscaling to {max_size}x{max_size} or lower. A 4096 texture uses 4x the VRAM of 2048. For non-critical assets, 1024 is often sufficient."
        })

    # 压缩格式检测（基于命名启发式）
    name_lower = asset_name.lower()
    inferred_type = None
    if any(k in name_lower for k in ["_n", "_normal", "_norm"]):
        inferred_type = "NormalMap"
    elif any(k in name_lower for k in ["_mra", "_orm", "_mask", "_ao", "_rough", "_metal"]):
        inferred_type = "Masks"
    elif any(k in name_lower for k in ["_bc", "_base", "_albedo", "_diffuse", "_color"]):
        inferred_type = "BaseColor"

    COMPRESSION_RULES = {
        "NormalMap": {
            "expected": [unreal.TextureCompressionSettings.TC_NORMALMAP, 
                         unreal.TextureCompressionSettings.TC_DEFAULT,
                         unreal.TextureCompressionSettings.TC_BC7],
            "forbidden": [unreal.TextureCompressionSettings.TC_GRAYSCALE,
                          unreal.TextureCompressionSettings.TC_MASKS],
            "reason": "NormalMap needs at least 2 channels (XY). TC_GRAYSCALE/MASKS only provide 1 channel, losing Z reconstruction data."
        },
        "BaseColor": {
            "expected": [unreal.TextureCompressionSettings.TC_DEFAULT,
                         unreal.TextureCompressionSettings.TC_BC7],
            "forbidden": [unreal.TextureCompressionSettings.TC_NORMALMAP],
            "reason": "BaseColor should not use TC_NORMALMAP. NormalMap compression (BC5) wastes channels for RGB data."
        },
        "Masks": {
            "expected": [unreal.TextureCompressionSettings.TC_MASKS,
                         unreal.TextureCompressionSettings.TC_DEFAULT,
                         unreal.TextureCompressionSettings.TC_BC7],
            "forbidden": [unreal.TextureCompressionSettings.TC_NORMALMAP,
                          unreal.TextureCompressionSettings.TC_GRAYSCALE],
            "reason": "Mask textures (MRA/ORM) should use TC_MASKS for independent channel precision, or TC_DEFAULT/BC7."
        }
    }

    if inferred_type and inferred_type in COMPRESSION_RULES:
        rule = COMPRESSION_RULES[inferred_type]
        if compression in rule["forbidden"]:
            violations.append({
                "asset_path": asset_path,
                "asset_name": asset_name,
                "asset_class": "Texture2D",
                "rule": "Texture_CompressionFormat",
                "severity": "Error",
                "current_value": compression.name,
                "threshold": " / ".join([e.name for e in rule["expected"]]),
                "message": f"{inferred_type} texture uses forbidden compression {compression.name}",
                "suggestion": f"{rule['reason']} Recommended: {' / '.join([e.name for e in rule['expected']])}."
            })

    return violations


def check_texture_compliance(folder_path="/Game", config=None):
    """
    规则2：扫描文件夹下的所有Texture2D

    【配置注入】
    config参数由pipeline统一传入，保证同轮扫描使用同一套配置。
    如果独立调用（如单规则测试），config为None时回退读取JSON。
    """
    folder_path = normalize_folder_path(folder_path)

    # 独立调用时回退读取配置
    if config is None:
        from validation.core.config_loader import get_config
        config = get_config()

    threshold = get_texture_config(config)
    exempt_paths = get_texture_exempt_paths(config)

    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    filter = unreal.ARFilter(package_paths=[folder_path], recursive_paths=True)
    asset_data_list = registry.get_assets(filter)

    if not asset_data_list:
        unreal.log("[INFO] [Rule2] No assets found in specified folder.")
        return []

    violations = []
    checked_count = 0

    for asset_data in asset_data_list:
        path = str(asset_data.package_name)
        if "__External" in path:
            continue

        asset_class = str(asset_data.asset_class_path.asset_name) if asset_data.asset_class_path else "None"
        if asset_class != "Texture2D":
            continue

        checked_count += 1

        try:
            asset = asset_data.get_asset()
            if asset is None:
                continue
            tex = unreal.Texture2D.cast(asset)
            if tex is None:
                continue
        except Exception as e:
            unreal.log_warning(f"[WARNING] [Rule2] Failed to load asset {path}: {e}")
            continue

        asset_name = str(asset_data.asset_name)
        v = _check_single_texture(tex, asset_name, path, threshold, exempt_paths)
        violations.extend(v)

    unreal.log(f"[OK] [Rule2] Checked {checked_count} Textures, found {len(violations)} violations.")
    return violations


def check_texture_compliance_on_selected(selected_assets=None, config=None):
    """
    规则2：扫描选中的资产（内容浏览器选中）

    【配置注入】
    config参数由pipeline统一传入，保证同轮扫描使用同一套配置。
    """
    if selected_assets is None:
        selected_assets = unreal.EditorUtilityLibrary.get_selected_assets()

    if not selected_assets:
        unreal.log_warning("[WARNING] [Rule2] No assets selected.")
        return []

    # 独立调用时回退读取配置
    if config is None:
        from validation.core.config_loader import get_config
        config = get_config()

    threshold = get_texture_config(config)
    exempt_paths = get_texture_exempt_paths(config)
    violations = []
    checked_count = 0

    for asset in selected_assets:
        asset_class = asset.get_class().get_name()
        if asset_class != "Texture2D":
            continue

        checked_count += 1
        asset_name = asset.get_name()
        asset_path = asset.get_path_name()

        v = _check_single_texture(asset, asset_name, asset_path, threshold, exempt_paths)
        violations.extend(v)

    unreal.log(f"[OK] [Rule2] Checked {checked_count} selected Textures, found {len(violations)} violations.")
    return violations


def print_violations(violations):
    if not violations:
        unreal.log("[OK] [Rule2] All Textures passed compliance validation.")
        return

    unreal.log_warning(f"[WARNING] [Rule2] Found {len(violations)} violations:")
    for v in violations:
        severity = v.get("severity", "Warning")
        msg = f"[{severity}] {v['asset_name']} | {v['rule']}: {v['message']}"
        if severity == "Error":
            unreal.log_error(msg)
        else:
            unreal.log_warning(msg)
        unreal.log(f"   -> Fix: {v['suggestion']}")


def run_rule2(folder_path="/Game"):
    violations = check_texture_compliance(folder_path)
    print_violations(violations)
    return violations


def run_rule2_on_selected():
    violations = check_texture_compliance_on_selected()
    print_violations(violations)
    return violations