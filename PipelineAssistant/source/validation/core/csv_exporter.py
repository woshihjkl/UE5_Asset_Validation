import csv
import os
import sys
import unreal
from datetime import datetime
from collections import defaultdict

_current_file = os.path.abspath(__file__)
_source_dir = os.path.dirname(os.path.dirname(os.path.dirname(_current_file)))
if _source_dir not in sys.path:
    sys.path.insert(0, _source_dir)


# =============================================================================
# 【业务层】
# 资产质检报告是管线闭环的最后一步：美术修完资产→扫描→出报告→按报告整改。
# 生产环境用CSV（结构化、可筛选、供下游系统消费），人工阅读用MD（聚合、醒目、Git归档）。
# =============================================================================

def get_output_directory(config):
    """
    【标准层】获取报告输出目录，优先读取配置，失败则回退到项目Saved目录。
    """
    output_config = config.get("Output", {})
    output_dir = output_config.get("CSVOutputDir", "")
    
    if not output_dir or str(output_dir).strip() == "":
        # 【引擎层】UE Python API：Paths.project_dir() 获取项目根目录
        project_dir = unreal.Paths.project_dir()
        output_dir = os.path.join(project_dir, "Saved", "ValidationReports")
    
    # 【边界层】目录创建失败回退桌面，避免崩溃
    try:
        os.makedirs(output_dir, exist_ok=True)
    except Exception as e:
        unreal.log_warning(f"[WARNING] Failed to create output dir {output_dir}: {e}")
        output_dir = os.path.join(os.path.expanduser("~"), "Desktop")
        os.makedirs(output_dir, exist_ok=True)
    
    return output_dir


def _should_export_csv(config):
    """读取配置开关，默认True"""
    output_config = config.get("Output", {})
    return output_config.get("export_csv", True)


def _should_export_md(config):
    """读取配置开关，默认True"""
    output_config = config.get("Output", {})
    return output_config.get("export_md", True)


def _format_display_value(rule, current):
    """
    【标准层】将原始检测值格式化为人类可读字符串。
    """
    rule = str(rule)
    if "LOD" in rule:
        return f"{current}层"
    elif "LightmapUV" in rule or "UVChannel" in rule:
        return f"{current}套"
    elif "HardReference" in rule or "MissingReference" in rule:
        return f"缺失：{current}"
    elif "Compression" in rule:
        return str(current)
    else:
        return str(current)


def _format_display_threshold(rule, threshold):
    """
    【标准层】将阈值格式化为人类可读标准。
    """
    rule = str(rule)
    if "Triangle" in rule or "Vertex" in rule or "MaxSize" in rule or "Count" in rule:
        return f"≤{threshold}"
    elif "LOD" in rule or "LightmapUV" in rule or "UVChannel" in rule:
        return f"≥{threshold}"
    elif "HardReference" in rule or "MissingReference" in rule:
        return "依赖资源需存在"
    elif "Compression" in rule:
        return f"需为 {threshold}"
    elif "PowerOfTwo" in rule:
        return "宽高需为2的幂"
    else:
        return str(threshold)


def export_to_csv(violations, csv_path):
    """
    【管线思维】CSV是生产格式：一行一条违规，9字段完整保留，供Excel筛选和自动化调用。
    """
    with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow([
            "AssetPath", "AssetName", "AssetClass", "RuleName",
            "Severity", "CurrentValue", "Threshold", "Message", "Suggestion"
        ])
        for v in violations:
            writer.writerow([
                v.get("asset_path", ""),
                v.get("asset_name", ""),
                v.get("asset_class", ""),
                v.get("rule", ""),
                v.get("severity", ""),
                v.get("current_value", ""),
                v.get("threshold", ""),
                v.get("message", ""),
                v.get("suggestion", "")
            ])
    
    unreal.log(f"[OK] CSV exported: {csv_path}")


def export_to_markdown(violations, summary, md_path, scan_scope):
    """
    【管线思维】MD是展示格式：按资产聚合、Error优先分层、符号醒目，主打人工阅读。
    
    【边界层】
    - 无Error时显示 ✅ 无违规项
    - 无Warning时显示 ✅ 无违规项
    - 同一资产有Error则归Error板块（显示全部违规），Warning板块不再重复
    """
    # ========== 统计 ==========
    unique_assets = set()
    error_count = 0
    warning_count = 0
    
    for v in violations:
        unique_assets.add(v.get("asset_name", "Unknown"))
        if v.get("severity") == "Error":
            error_count += 1
        else:
            warning_count += 1
    
    # ========== 按资产分组 ==========
    asset_violations = defaultdict(list)
    for v in violations:
        asset_name = v.get("asset_name", "Unknown")
        asset_violations[asset_name].append(v)
    
    # ========== 分类：有Error的资产归Error板块，纯Warning归Warning板块 ==========
    error_section = {}   # {asset_name: [all_violations_for_this_asset]}
    warning_section = {} # {asset_name: [warning_violations_only]}
    
    for asset_name, v_list in asset_violations.items():
        has_error = any(v.get("severity") == "Error" for v in v_list)
        if has_error:
            # Error板块显示该资产全部违规（Error+Warning），方便一次性修完
            error_section[asset_name] = v_list
        else:
            # 纯Warning资产
            warning_section[asset_name] = v_list
    
    # ========== 排序：按违规数量从多到少 ==========
    error_section = dict(sorted(error_section.items(), key=lambda x: len(x[1]), reverse=True))
    warning_section = dict(sorted(warning_section.items(), key=lambda x: len(x[1]), reverse=True))
    
    # ========== 生成MD ==========
    lines = []
    now_str = datetime.now().strftime("%Y.%m.%d %H:%M")
    
    lines.append(f"# Asset Validation Report — {now_str}")
    lines.append(f"> 扫描范围：{scan_scope}")
    lines.append(f"> 扫描资产总数：{summary.get('total_checked', 'N/A')}")
    lines.append(f"> 违规资产总数：{len(unique_assets)}")
    lines.append(f"> 🔴 Error：{error_count}项 | 🟡 Warning：{warning_count}项")
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # ========== Error 板块 ==========
    lines.append("## 🔴 Error（优先处理）")
    lines.append("")
    
    if not error_section:
        lines.append("✅ 无违规项")
        lines.append("")
    else:
        for asset_name, v_list in error_section.items():
            lines.append(f"### {asset_name}")
            lines.append("| 规则 | 当前值 | 标准 |")
            lines.append("|------|--------|------|")
            for v in v_list:
                rule = v.get("rule", "").replace("StaticMesh_", "").replace("Texture_", "")
                current = _format_display_value(v.get("rule"), v.get("current_value"))
                threshold = _format_display_threshold(v.get("rule"), v.get("threshold"))
                lines.append(f"| {rule} | {current} | {threshold} |")
            lines.append("")
    
    lines.append("---")
    lines.append("")
    
    # ========== Warning 板块 ==========
    lines.append("## 🟡 Warning（次要处理）")
    lines.append("")
    
    if not warning_section:
        lines.append("✅ 无违规项")
        lines.append("")
    else:
        for asset_name, v_list in warning_section.items():
            lines.append(f"### {asset_name}")
            lines.append("| 规则 | 当前值 | 标准 |")
            lines.append("|------|--------|------|")
            for v in v_list:
                rule = v.get("rule", "").replace("StaticMesh_", "").replace("Texture_", "")
                current = _format_display_value(v.get("rule"), v.get("current_value"))
                threshold = _format_display_threshold(v.get("rule"), v.get("threshold"))
                lines.append(f"| {rule} | {current} | {threshold} |")
            lines.append("")
    
    lines.append("---")
    lines.append("")
    lines.append("> 完整原始数据与修复建议见同名 CSV 文件")
    lines.append("> 生成工具：UE5 Asset Validation Pipeline")
    
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))
    
    unreal.log(f"[OK] MD report exported: {md_path}")


def export_validation_result(result, scan_scope="Unknown"):
    """
    【管线思维】统一入口：同一份内存数据，分别渲染 CSV（生产）和 MD（展示）。
    
    Args:
        result: pipeline返回的dict {"all_violations": [...], "summary": {...}}
        scan_scope: 扫描范围描述（如 "/Game Full Scan" 或 "Selected Assets (3 items)"）
    
    Returns:
        str: 导出的主文件路径（CSV优先），无违规返回None
    """
    config = result.get("config", {})
    violations = result.get("all_violations", [])
    summary = result.get("summary", {})
    
    if not violations:
        unreal.log("[INFO] No violations to export.")
        return None
    
    # 【标准层】统一时间戳，确保CSV和MD一一对应
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"AssetValidation_{timestamp}"
    
    output_dir = get_output_directory(config)
    csv_path = os.path.join(output_dir, f"{base_name}.csv")
    md_path = os.path.join(output_dir, f"{base_name}.md")
    
    exported = []
    
    if _should_export_csv(config):
        export_to_csv(violations, csv_path)
        exported.append(csv_path)
    
    if _should_export_md(config):
        export_to_markdown(violations, summary, md_path, scan_scope)
        exported.append(md_path)
    
    if exported:
        return exported[0]  # 保持原有返回习惯，返回CSV路径
    else:
        unreal.log_warning("[WARNING] Both CSV and MD export disabled in config.")
        return None