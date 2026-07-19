import unreal
from ..utils import normalize_folder_path


def scan_assets(folder_path="/Game"):
    """
    扫描指定目录下的所有资产

    先提取资产注册表。
    根据扫描规则，直接查出选定文件夹及其子文件夹里所有资产的元数据列表。
    遍历这个列表，把每个资产的物理路径字符串化，并过滤掉包含 __External 的垃圾文件。
    再获取资产的类型路径，如果类型路径存在，就提取它的类名；如果不存在，就赋值为 "None"。
    最后把资产的名称、路径、类名打包成字典，汇总返回。

    :param folder_path: 目录路径，例如 "/Game/Characters"
    :return: 资产列表 [{name, path, class}]
    """
    folder_path = normalize_folder_path(folder_path)  #  normalize_folder_path 会将 "Characters" 自动补全为 "/Game/Characters"
    
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    
    filter = unreal.ARFilter(
        package_paths=[folder_path],
        recursive_paths=True
    )
    
    # 防御：Asset Registry 未就绪时可能返回 None
    asset_data_list = registry.get_assets(filter)
    if not asset_data_list:
        return []
    
    result = []
    for asset_data in asset_data_list:
        # 过滤掉 __ExternalActors__ 和 __ExternalObjects__
        path = str(asset_data.package_name)
        if "__External" in path:
            continue
        
        # 获取资产类名
        asset_class = str(asset_data.asset_class_path.asset_name) if asset_data.asset_class_path else "None"
        
        result.append({
            "name": str(asset_data.asset_name),
            "path": path,
            "class": asset_class
        })
    
    return result