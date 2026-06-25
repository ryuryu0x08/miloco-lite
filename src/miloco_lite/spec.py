"""设备 spec：从 miot-spec.org 公开接口拉取（免授权）并解析。

spec 由设备 urn 决定，urn 来自设备列表的 spec_type 字段。
"""
from __future__ import annotations

import httpx

from .const import SPEC_INSTANCE_URL
from .devices import build_device_list
from .errors import MilocoLiteError


def urn_of_did(did: str) -> tuple[str, dict]:
    """从设备列表里找到 did 的 urn 及基本信息。

    注意：为拿 urn 需要先拉一次设备列表（urn 不在本地缓存）。
    """
    for d in build_device_list():
        if d["did"] == did:
            if not d.get("urn"):
                raise MilocoLiteError(f"设备 {did} 无 urn(spec_type)，无法查 spec")
            return d["urn"], d
    raise MilocoLiteError(f"did {did} 不在设备列表中")


def fetch_instance(urn: str) -> dict:
    """GET miot-spec.org 标准 instance 定义（公开、免授权）。"""
    with httpx.Client(timeout=30) as c:
        r = c.get(SPEC_INSTANCE_URL, params={"type": urn})
    if r.status_code != 200:
        raise MilocoLiteError(f"拉取 spec 失败 HTTP {r.status_code}（urn={urn}）")
    obj = r.json()
    if "services" not in obj:
        raise MilocoLiteError(f"spec instance 格式异常: {str(obj)[:200]}")
    return obj


def _short_type(type_str: str) -> str:
    """urn:miot-spec-v2:property:on:00000006:... -> 'on'"""
    parts = type_str.split(":")
    return parts[3] if len(parts) > 3 else type_str


def _fmt_constraint(p: dict) -> str:
    """把 value-list / value-range 拼成可读约束。"""
    if "value-list" in p:
        return ",".join(
            f"{v.get('description', v.get('value'))}={v['value']}" for v in p["value-list"]
        )
    vr = p.get("value-range")
    if isinstance(vr, list) and len(vr) >= 3:
        return f"[{vr[0]},{vr[1]};{vr[2]}]"  # [min,max,step]
    return ""


def parse(instance: dict) -> dict:
    """提取 services 下的 properties / actions 成扁平可读结构。"""
    props, actions = [], []
    for svc in instance.get("services", []):
        siid = svc.get("iid")
        for p in svc.get("properties", []):
            access = p.get("access", [])
            acc = ("r" if "read" in access else "") + ("w" if "write" in access else "")
            acc = {"rw": "wr", "r": "r", "w": "w", "": "-"}.get(acc, acc)
            props.append({
                "iid": f"{siid}.{p.get('iid')}",
                "name": _short_type(p.get("type", "")),
                "access": acc,
                "format": p.get("format", ""),
                "constraint": _fmt_constraint(p),
                "unit": p.get("unit", ""),
            })
        for a in svc.get("actions", []):
            actions.append({
                "iid": f"{siid}.{a.get('iid')}",
                "name": _short_type(a.get("type", "")),
                "in": a.get("in", []),
            })
    return {"properties": props, "actions": actions}
