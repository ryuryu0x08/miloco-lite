"""本地状态存储：device_id 与 token。

存于 ``$MILOCO_LITE_HOME``（默认 ~/.openclaw/miloco-lite/）：
  - device_id：首次生成后持久化，OAuth state 由它派生，刷新登录都依赖它不变
  - token.json：access_token / refresh_token / expires_ts
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path

from .const import PROJECT_CODE

HOME = Path(
    os.environ.get("MILOCO_LITE_HOME", Path.home() / ".openclaw" / "miloco-lite")
)
TOKEN_FILE = HOME / "token.json"
DEVICE_ID_FILE = HOME / "device_id"


def load_or_make_device_id() -> str:
    """device_id 形如 ``mico.<uuid hex>``，首次生成后持久化。"""
    if DEVICE_ID_FILE.exists():
        return DEVICE_ID_FILE.read_text(encoding="utf-8").strip()
    did = f"{PROJECT_CODE}.{uuid.uuid4().hex}"
    HOME.mkdir(parents=True, exist_ok=True)
    DEVICE_ID_FILE.write_text(did, encoding="utf-8")
    return did


def state_of(device_id: str) -> str:
    """OAuth state = sha1("d=" + device_id)，与官方 MIoTOAuth2Client 一致。"""
    return hashlib.sha1(f"d={device_id}".encode("utf-8")).hexdigest()


def save_token(info: dict) -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(
        json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_token() -> dict | None:
    if not TOKEN_FILE.exists():
        return None
    try:
        return json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
