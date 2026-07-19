import json
import os
import unreal
import sys

# 配置文件路径（项目根目录）
CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "AuditRules.json"
)


def load_config(config_path=None):
    """
    加载JSON配置文件

    【工程思维】
    - 配置文件与代码分离，方便不同项目复用
    - try-except兜底，异常时回退硬编码默认值（任务书R4备选方案）
    - 极简设计：不做热重载、不做GUI编辑、不做多配置切换

    Args:
        config_path: 配置文件路径，默认项目根目录的AuditRules.json

    Returns:
        dict: 配置字典
    """
    if config_path is None:
        config_path = CONFIG_PATH

    # 默认值（硬编码回退）
    default_config = {
        "StaticMesh": {
            "Character": {"MaxTriangles": 50000, "MaxVertices": 80000, "MinLODCount": 2},
            "Prop": {"MaxTriangles": 20000, "MaxVertices": 40000, "MinLODCount": 2},
            "Vegetation": {"MaxTriangles": 15000, "MaxVertices": 30000, "MinLODCount": 2},
            "LODExemptPaths": ["/Game/LevelPrototyping", "/Game/Fab", "/Game/Blockout"]
        },
        "Texture": {
            "MaxSize": 2048,
            "RequirePowerOfTwo": True,
            "ExemptPaths": ["/Game/UI", "/Game/HUD"]
        },
        "LightmapUV": {
            "RequireChannel2": True
        },
        "Output": {
            "CSVOutputDir": ""
        }
    }

    # 如果配置文件不存在，创建默认配置并保存
    if not os.path.exists(config_path):
        unreal.log_warning(f"[CONFIG] Config file not found: {config_path}")
        unreal.log("[CONFIG] Using default hardcoded thresholds.")
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=4, ensure_ascii=False)
            unreal.log(f"[CONFIG] Default config created at: {config_path}")
        except Exception as e:
            unreal.log_error(f"[CONFIG] Failed to create default config: {e}")
        return default_config

    # 读取配置文件
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        unreal.log(f"[CONFIG] Loaded config from: {config_path}")
        return config
    except json.JSONDecodeError as e:
        unreal.log_error(f"[CONFIG] Invalid JSON format: {e}")
        unreal.log("[CONFIG] Fallback to default thresholds.")
        return default_config
    except Exception as e:
        unreal.log_error(f"[CONFIG] Failed to load config: {e}")
        unreal.log("[CONFIG] Fallback to default thresholds.")
        return default_config


def get_config():
    """
    获取配置（每次调用重新读取JSON）

    【设计变更】
    原方案使用全局缓存(_CONFIG)和reload_config()，存在两个问题：
    1. 热更新需要显式调用reload，容易遗漏
    2. 同轮扫描中各规则可能读到不同版本的配置（竞态）

    新方案：pipeline统一读取一次，传给所有规则。
    每次扫描重新读取，天然热更新，保证同轮扫描的原子性。
    """
    return load_config()


def get_output_config():
    """获取输出配置（CSV路径等）"""
    config = get_config()
    return config.get("Output", {})