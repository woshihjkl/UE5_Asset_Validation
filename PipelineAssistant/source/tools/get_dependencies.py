import unreal
from ..utils import normalize_asset_path


def get_dependencies(asset_path):
    """
    查询指定资产的直接依赖资源（硬依赖）

    选中资产后，把资产的路径对象化后获得资产数据，然后根据硬依赖筛选一些，筛选过后的还要过滤掉引擎内部和__External
    然后剩下的再对象化，然后再根据对象化的数据去查询，查到返回，查不到就标记Unknown。

    Args:
        asset_path: 资产路径，支持 object_path（/Game/.../Asset.Asset）或 package_name（/Game/.../Asset）
    
    Returns:
        list: 依赖资产列表，每个元素包含 name, path, class。资产未找到时返回空列表。
    """
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    
    # 使用 utils 统一规范化资产路径
    asset_path = normalize_asset_path(asset_path)
    if not asset_path:
        return []
    
    # 获取资产数据
    asset_data = registry.get_asset_by_object_path(asset_path)
    
    if not asset_data.is_valid():
        return []
    
    # 获取硬依赖（显式设置参数，确保跨版本兼容）
    package_name = unreal.Name(str(asset_data.package_name))
    dependency_options = unreal.AssetRegistryDependencyOptions(
        include_hard_package_references=True,
        include_soft_package_references=False,
        include_searchable_names=False,
        include_soft_management_references=False,
        include_hard_management_references=False
    )
    dependency_names = registry.get_dependencies(package_name, dependency_options)
    
    # 防御：如果返回 None（查询失败），转为空列表
    if dependency_names is None:
        return []
    
    result = []
    seen = set()  # 去重用
    
    for dep_name in dependency_names:
        dep_path_str = str(dep_name)
        
        # 过滤引擎内部资源和外部 Actor 垃圾数据
        if dep_path_str.startswith("/Engine/"):
            continue
        if "__External" in dep_path_str:
            continue
        
        # 去重：避免同一依赖多次出现
        if dep_path_str in seen:
            continue
        seen.add(dep_path_str)
        
        # 构造完整的 object path 查询依赖资产详情
        dep_asset_name = dep_path_str.split("/")[-1]
        full_object_path = f"{dep_path_str}.{dep_asset_name}"
        
        dep_data = registry.get_asset_by_object_path(full_object_path)
        
        if dep_data.is_valid():
            # 提取 class 的 asset_name（如 "Skeleton", "MaterialInstanceConstant"）
            class_path = dep_data.asset_class_path
            class_name = str(class_path.asset_name) if hasattr(class_path, 'asset_name') else str(class_path)
            
            result.append({
                "name": str(dep_data.asset_name),
                "path": dep_path_str,
                "class": class_name
            })
        else:
            result.append({
                "name": dep_asset_name,
                "path": dep_path_str,
                "class": "Unknown"
            })
    
    return result