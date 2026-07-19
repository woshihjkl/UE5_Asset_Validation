import unreal
import sys
import os

_current_file = os.path.abspath(__file__)
_source_dir = os.path.dirname(os.path.dirname(os.path.dirname(_current_file)))
if _source_dir not in sys.path:
    sys.path.insert(0, _source_dir)

from validation.core.pipeline import (
    run_full_validation,
    run_full_validation_on_selected_folders,
    run_full_validation_on_selected_assets
)
from validation.core.csv_exporter import export_validation_result


# 【边界层】防重入锁：UE ToolMenus 有时会触发两次命令，导致重复扫描和重复导出
_scanning = False


def smart_validation_scan(asset_category="Prop"):
    """
    【管线思维】智能检测入口：根据当前选中内容自动判断扫描范围。
    
    判断优先级：
    1. 如果有选中资产 → 扫描选中资产
    2. 如果有选中文件夹 → 扫描选中文件夹
    3. 如果都没选 → 扫描整个 /Game
    """
    global _scanning
    if _scanning:
        unreal.log_warning("[WARNING] Scan already in progress, skipping duplicate trigger.")
        return None
    _scanning = True
    
    try:
        selected_assets = unreal.EditorUtilityLibrary.get_selected_assets()
        if selected_assets and len(selected_assets) > 0:
            unreal.log(f"[INFO] Detected {len(selected_assets)} selected assets, running asset-level scan.")
            result = run_full_validation_on_selected_assets(asset_category)
            scan_scope = f"Selected Assets ({len(selected_assets)} items)"
        else:
            selected_folders = unreal.EditorUtilityLibrary.get_selected_folder_paths()
            if selected_folders and len(selected_folders) > 0:
                unreal.log(f"[INFO] Detected selected folder: {selected_folders[0]}, running folder scan.")
                result = run_full_validation_on_selected_folders(asset_category)
                scan_scope = f"Folder: {selected_folders[0]}"
            else:
                unreal.log("[INFO] No selection detected, running full /Game scan.")
                result = run_full_validation("/Game", asset_category)
                scan_scope = "/Game Full Scan"
        
        if result:
            # 【管线思维】传入扫描范围，确保MD报告头部信息准确
            csv_path = export_validation_result(result, scan_scope=scan_scope)
            if csv_path:
                unreal.log(f"[OK] Report exported to: {csv_path}")
            else:
                unreal.log("[INFO] No violations found, report not exported.")
        
        return result
        
    finally:
        _scanning = False


def register_validation_toolbar_button():
    """
    在UE编辑器工具栏注册"资产质检"按钮
    """
    menus = unreal.ToolMenus.get()
    
    window_menu = menus.find_menu("LevelEditor.MainMenu.Window")
    if not window_menu:
        unreal.log_error("[ERROR] Failed to find Window menu")
        return False
    
    try:
        entry = unreal.ToolMenuEntry(
            name="RunAssetValidation",
            type=unreal.MultiBlockType.MENU_ENTRY
        )
        entry.set_label("Run Asset Validation")
        entry.set_string_command(
            unreal.ToolMenuStringCommandType.PYTHON,
            custom_type="",
            string="import sys; sys.path.append(r'D:\\UE_Project\\AAAProjects\\PipelineAssistant\\source'); from validation.core.toolbar_button import smart_validation_scan; smart_validation_scan(asset_category='Prop')"
        )
        window_menu.add_menu_entry("Validation", entry)
        
        menus.refresh_all_widgets()
        unreal.log("[OK] Validation button registered under Window menu")
        return True
        
    except Exception as e:
        unreal.log_error(f"[ERROR] Failed to register toolbar button: {e}")
        return False


def reregister_button():
    """
    重新注册按钮（改代码后调用，无需重启UE）
    """
    menus = unreal.ToolMenus.get()
    window_menu = menus.find_menu("LevelEditor.MainMenu.Window")
    
    if not window_menu:
        unreal.log_error("[ERROR] Failed to find Window menu")
        return False
    
    try:
        window_menu.remove_entry("RunAssetValidation")
        unreal.log("[INFO] Old button removed.")
    except Exception as e:
        unreal.log(f"[INFO] No old button to remove: {e}")
    
    result = register_validation_toolbar_button()
    

    
    if result:
        unreal.log("[OK] Button re-registered successfully. No need to restart UE.")
    
    return result


# 注册按钮
register_validation_toolbar_button()