import os


def normalize_folder_path(path):
    """
    规范化文件夹路径

    - 确保以 / 开头
    - 去掉末尾多余的 /
    - 空路径回退到 /Game
    """
    if not path:
        return "/Game"
    path = path.strip()
    if not path.startswith("/"):
        path = "/" + path
    return path.rstrip("/")


def normalize_asset_path(path):
    """
    规范化资产路径

    - 确保以 / 开头
    - 空路径返回空字符串（表示无效）
    """
    if not path:
        return ""
    path = path.strip()
    if not path.startswith("/"):
        path = "/" + path
    return path


def is_path_exempt(asset_path, exempt_paths):
    """
    判断资产是否位于白名单目录。

    【设计意图】
    统一所有 Rule 的白名单匹配逻辑，避免各 Rule 各自实现导致行为不一致。
    以后白名单规则升级（正则、Metadata、Tag），只需改这里，所有 Rule 自动生效。

    匹配规则：
    - /Game/Test       -> 命中（精确匹配）
    - /Game/Test/AAA   -> 命中（子目录）
    - /Game/TestAssets -> 不命中（不是子目录）
    - /Game/Test123    -> 不命中（不是子目录）

    Args:
        asset_path: 资产路径（如 /Game/Props/SM_Chair）
        exempt_paths: 白名单路径列表（如 ["/Game/Test", "/Game/WIP"]）

    Returns:
        bool: 是否命中白名单
    """
    asset_path = asset_path.rstrip("/")

    for exempt in exempt_paths:
        exempt = exempt.rstrip("/")

        if asset_path == exempt:
            return True

        if asset_path.startswith(exempt + "/"):
            return True

    return False