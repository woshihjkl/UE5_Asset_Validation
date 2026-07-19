import sys

# 添加 source 目录到路径（不是项目根目录）
source_path = r"D:\UE_Project\AAAProjects\PipelineAssistant\source"
if source_path not in sys.path:
    sys.path.append(source_path)

# 启动时自动注册按钮
try:
    from validation.core.toolbar_button import register_validation_toolbar_button
    register_validation_toolbar_button()
    print("[INIT] Asset Validation Pipeline initialized.")
except Exception as e:
    print(f"[INIT] Failed to initialize: {e}")