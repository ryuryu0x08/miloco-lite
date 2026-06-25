"""miloco-lite 自定义异常。"""
from __future__ import annotations


class MilocoLiteError(Exception):
    """所有可预期错误的统一类型；CLI 层捕获后以 JSON 输出并退出码 3。"""
