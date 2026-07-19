import unreal
import sys
import os

_current_file = os.path.abspath(__file__)
_source_dir = os.path.dirname(os.path.dirname(os.path.dirname(_current_file)))
if _source_dir not in sys.path:
    sys.path.insert(0, _source_dir)

from utils import normalize_folder_path

from validation.core.config_loader import get_config

from validation.rules.rule1_static_mesh import (
    check_static_mesh_performance,
    check_static_mesh_performance_on_selected
)
from validation.rules.rule2_texture import (
    check_texture_compliance,
    check_texture_compliance_on_selected
)
from validation.rules.rule3_lightmap_uv import (
    check_lightmap_uv,
    check_lightmap_uv_on_selected
)
from validation.rules.rule4_hard_reference import (
    check_hard_reference_integrity,
    check_hard_reference_on_selected
)


def run_full_validation(folder_path="/Game", asset_category="Prop"):
    """
    执行全部4条规则的批量扫描（文件夹模式）

    【管线思维】
    不是孤立地跑4个脚本，而是统一的入口：
    - 一次扫描，全部规则执行
    - 统一输出格式，方便CSV导出
    - 统一日志分级（Error/Warning/Info）

    【配置注入】
    每次扫描重新读取AuditRules.json，将config注入各规则。
    保证同轮扫描所有规则使用同一套配置，天然支持热更新。

    Args:
        folder_path: 扫描目录
        asset_category: StaticMesh类型阈值（Character/Prop/Vegetation）

    Returns:
        dict: {
            "all_violations": [...],
            "summary": {
                "total_checked": ...,
                "total_violations": ...,
                "by_rule": {...}
            }
        }
    """
    # 每次扫描重新读取配置，本轮所有规则共用这一份
    config = get_config()

    unreal.log("=" * 60)
    unreal.log("[SCAN] UE5 Asset Validation Pipeline - Full Scan")
    unreal.log(f"[TARGET] Folder: {folder_path}")
    unreal.log("=" * 60)

    all_violations = []

    unreal.log("\n[RULE 1] StaticMesh Performance")
    v1 = check_static_mesh_performance(folder_path, asset_category, config)
    all_violations.extend(v1)

    unreal.log("\n[RULE 2] Texture Compliance")
    v2 = check_texture_compliance(folder_path, config)
    all_violations.extend(v2)

    unreal.log("\n[RULE 3] Lightmap UV")
    v3 = check_lightmap_uv(folder_path, config)
    all_violations.extend(v3)

    unreal.log("\n[RULE 4] Hard Reference Integrity")
    v4 = check_hard_reference_integrity(folder_path, config)
    all_violations.extend(v4)

    summary = {
        "total_checked": "See individual rule logs",
        "total_violations": len(all_violations),
        "by_rule": {
            "StaticMesh_Performance": len(v1),
            "Texture_Compliance": len(v2),
            "Lightmap_UV": len(v3),
            "HardReference": len(v4)
        }
    }

    unreal.log("\n" + "=" * 60)
    unreal.log("[SUMMARY] Validation Summary")
    unreal.log("=" * 60)
    unreal.log(f"Total Violations: {len(all_violations)}")
    unreal.log(f"  - Rule 1 (StaticMesh): {len(v1)}")
    unreal.log(f"  - Rule 2 (Texture): {len(v2)}")
    unreal.log(f"  - Rule 3 (Lightmap UV): {len(v3)}")
    unreal.log(f"  - Rule 4 (Hard Reference): {len(v4)}")

    if all_violations:
        unreal.log_error("[FAIL] Validation FAILED. Please fix violations above.")
    else:
        unreal.log("[PASS] All validations PASSED.")

    return {
        "config": config,
        "all_violations": all_violations,
        "summary": summary
    }


def run_full_validation_on_selected_folders(asset_category="Prop"):
    """
    执行全部4条规则的批量扫描（选中文件夹模式）

    获取内容浏览器中选中的文件夹路径，执行扫描。
    注意：UE 5.7.4 返回的路径可能带 /All/ 前缀，需要去掉。
    """
    # 每次扫描重新读取配置
    config = get_config()

    selected = unreal.EditorUtilityLibrary.get_selected_folder_paths()
    if not selected:
        unreal.log_warning("[WARNING] No folder selected in Content Browser.")
        return None

    folder_path = str(selected[0])
    # UE 5.7.4 get_selected_folder_paths() 返回 /All/Game/... 格式
    # 需要去掉 /All/ 前缀，变成 /Game/...
    if folder_path.startswith("/All/"):
        folder_path = folder_path[4:]  # 去掉 "/All/"

    return run_full_validation(folder_path, asset_category)


def run_full_validation_on_selected_assets(asset_category="Prop"):
    """
    执行全部4条规则的批量扫描（选中资产模式）

    获取内容浏览器中选中的具体资产，执行检测。
    更灵活，适合美术只想检查刚导入的几个资产。
    """
    # 每次扫描重新读取配置
    config = get_config()

    selected = unreal.EditorUtilityLibrary.get_selected_assets()
    if not selected:
        unreal.log_warning("[WARNING] No assets selected in Content Browser.")
        return None

    unreal.log("=" * 60)
    unreal.log("[SCAN] UE5 Asset Validation Pipeline - Selected Assets")
    unreal.log(f"[TARGET] {len(selected)} selected assets")
    unreal.log("=" * 60)

    all_violations = []

    unreal.log("\n[RULE 1] StaticMesh Performance")
    v1 = check_static_mesh_performance_on_selected(selected, asset_category, config)
    all_violations.extend(v1)

    unreal.log("\n[RULE 2] Texture Compliance")
    v2 = check_texture_compliance_on_selected(selected, config)
    all_violations.extend(v2)

    unreal.log("\n[RULE 3] Lightmap UV")
    v3 = check_lightmap_uv_on_selected(selected, config)
    all_violations.extend(v3)

    unreal.log("\n[RULE 4] Hard Reference Integrity")
    v4 = check_hard_reference_on_selected(selected, config)
    all_violations.extend(v4)

    summary = {
        "total_checked": len(selected),
        "total_violations": len(all_violations),
        "by_rule": {
            "StaticMesh_Performance": len(v1),
            "Texture_Compliance": len(v2),
            "Lightmap_UV": len(v3),
            "HardReference": len(v4)
        }
    }

    unreal.log("\n" + "=" * 60)
    unreal.log("[SUMMARY] Validation Summary")
    unreal.log("=" * 60)
    unreal.log(f"Total Violations: {len(all_violations)}")
    unreal.log(f"  - Rule 1 (StaticMesh): {len(v1)}")
    unreal.log(f"  - Rule 2 (Texture): {len(v2)}")
    unreal.log(f"  - Rule 3 (Lightmap UV): {len(v3)}")
    unreal.log(f"  - Rule 4 (Hard Reference): {len(v4)}")

    if all_violations:
        unreal.log_error("[FAIL] Validation FAILED. Please fix violations above.")
    else:
        unreal.log("[PASS] All validations PASSED.")

    return {
        "config": config,
        "all_violations": all_violations,
        "summary": summary
    }