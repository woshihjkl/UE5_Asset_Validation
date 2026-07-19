# UE5_Asset_Validation

基于 Unreal Engine 5 Python 开发的轻量级资产规范检测工具。

该工具用于批量检测项目资源是否符合预设规范，支持 StaticMesh、Texture、Lightmap UV 以及 Hard Reference 等资源检查，并将检测结果导出为 CSV 报告，帮助快速定位资源问题。

------

## 功能

### StaticMesh

- Triangle 数量检测（LOD0）
- Vertex Count 检测（LOD0）
- LOD 层级数量检测

### Texture

- 最大尺寸检测
- 2 次幂尺寸检测
- Compression Settings 检测

### Lightmap

- Lightmap UV 通道检测

### Hard Reference

- 递归依赖检测
- 缺失资源检测

### 其它功能

- JSON 配置规则
- CSV 报告导出
- Window 菜单入口
- 自动初始化
- 热重载
- 白名单机制

------

## 项目结构

```text
UE5 Asset Validation Pipeline
│
├── README.md
├── DESIGN.md
├── AuditRules.json
│
├── Content/
│   └── Python/
│       └── init_unreal.py
│
├── source/
│   ├── validation/
│   │   ├── core/
│   │   ├── rules/
│   │   └── ...
│   └── tools/
│
└── docs/
```

------

## 快速开始

### 1. 放置项目文件

将工具放入项目目录，并保证 `Content/Python/init_unreal.py` 能够在编辑器启动时执行。

### 2. 配置检测规则

根据项目资源规范修改 `AuditRules.json`。

可配置内容包括：

- StaticMesh 检测阈值
- Texture 检测阈值
- Lightmap UV 配置
- 白名单目录
- CSV 输出目录

### 3. 启动编辑器

启动 Unreal Engine 后，工具会自动注册菜单。

在菜单中即可启动资产检测。

------

## 使用方式

工具根据当前编辑器状态自动选择扫描范围。

| 当前状态   | 扫描范围           |
| ---------- | ------------------ |
| 选中资产   | 当前资产           |
| 选中文件夹 | 当前文件夹（递归） |
| 无选择     | 全项目（`/Game`）  |

扫描完成后将在指定目录生成 CSV 检测报告。

------

## 配置示例

```json
{
    "StaticMesh": {
        "Character": {
            "MaxTriangles": 50000,
            "MaxVertices": 80000,
            "MinLODCount": 2
        }
    },
    "Texture": {
        "MaxSize": 2048
    },
    "LightmapUV": {
        "RequireChannel2": true
    }
}
```

更多配置说明请参考 `DESIGN.md`。

------

## 当前限制

当前版本存在以下限制：

- 仅检测 Hard Reference
- Lightmap UV 仅检测通道数量
- 不支持 Import Pipeline 自动检测
- 不包含自动修复功能

------

## 后续计划

计划继续完善以下内容：

- 增加 SkeletalMesh 检测
- 增加 Animation 检测
- 优化扫描性能
- 增加 HTML 检测报告
- 研究 Import Pipeline 扩展方案

------

## 开发环境

- Unreal Engine 5
- Python
- Unreal Python API
