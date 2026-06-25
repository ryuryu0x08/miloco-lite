"""miloco-lite —— 独立的小米米家设备 CLI（登录 + 查设备 + 控制设备）。

从 xiaomi-miloco 的 backend/miot 包提取出与小米云通信的最小子集，
去掉后端服务、感知引擎、规则引擎等一切重型依赖，做成可独立运行的 CLI。
"""
from .errors import MilocoLiteError

__version__ = "0.1.0"
__all__ = ["MilocoLiteError", "__version__"]
