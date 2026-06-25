"""会话与设备列表组装。

- get_client：读本地 token（过期自动刷新），返回可用 MiHomeClient
- build_device_list：gethome + device_list_page 组装成扁平设备列表
"""
from __future__ import annotations

import time

from .client import MiHomeClient
from .errors import MilocoLiteError
from .oauth import refresh
from .store import load_token, save_token


def get_client() -> MiHomeClient:
    """读本地 token，过期则刷新，返回可用 client。未登录则报错。"""
    tok = load_token()
    if not tok:
        raise MilocoLiteError("尚未登录，请先运行: miloco-lite login")
    if tok.get("expires_ts", 0) < time.time() + 60:
        tok = refresh(tok["refresh_token"])
        save_token(tok)
    return MiHomeClient(tok["access_token"])


def _device_row(d: dict, belong: dict[str, dict]) -> dict | None:
    """把一条云端设备记录 + 归属信息组装成扁平行。无 did 返回 None。"""
    did = d.get("did")
    if not did:
        return None
    b = belong.get(did, {"home": "", "room": ""})
    return {
        "did": did,
        "name": d.get("name", ""),
        "room": b["room"],
        "home": b["home"],
        "online": d.get("isOnline", False),
        "model": d.get("model", ""),
        "urn": d.get("spec_type", ""),
    }


def _build_belong(homelist: list[dict]) -> tuple[dict[str, dict], list[str]]:
    """从 gethome 结果构建 did→归属 映射 和 全部 did 列表。"""
    belong: dict[str, dict] = {}
    dids: list[str] = []
    for home in homelist:
        hname = home.get("name", "")
        for did in home.get("dids", []) or []:
            belong[did] = {"home": hname, "room": hname}
            dids.append(did)
        for room in home.get("roomlist", []) or []:
            rname = room.get("name", "")
            for did in room.get("dids", []) or []:
                belong[did] = {"home": hname, "room": rname}
                dids.append(did)
    return belong, dids


def build_device_list() -> list[dict]:
    """返回扁平设备列表：[{did,name,room,home,online,model,urn}, ...]"""
    cli = get_client()
    belong, all_dids = _build_belong(cli.get_homes().get("homelist", []))
    all_dids = sorted(set(all_dids))
    if not all_dids:
        return []

    devices: list[dict] = []
    for i in range(0, len(all_dids), 150):
        batch = all_dids[i : i + 150]
        start_did: str | None = None
        while True:  # 分页：单批可能 has_more
            res = cli.device_list_page(batch, start_did=start_did)
            for d in res.get("list", []) or []:
                row = _device_row(d, belong)
                if row:
                    devices.append(row)
            start_did = res.get("next_start_did")
            if not (res.get("has_more") and start_did):
                break
    return devices
