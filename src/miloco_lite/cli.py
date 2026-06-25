"""CLI：参数解析与各命令实现。"""
from __future__ import annotations

import json
import sys
from typing import Any

from . import oauth, spec
from .client import MiHomeClient
from .devices import build_device_list, get_client
from .errors import MilocoLiteError
from .store import load_or_make_device_id, load_token, save_token, state_of


def _out(obj: Any) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _parse_iid(iid: str) -> tuple[int, int]:
    """'2.1' / 'prop.2.1' / 'action.2.1' -> (2, 1)"""
    parts = iid.replace("prop.", "").replace("action.", "").split(".")
    if len(parts) != 2:
        raise MilocoLiteError(f"iid 格式应为 siid.piid，如 2.1，收到: {iid}")
    return int(parts[0]), int(parts[1])


def _infer_value(raw: str) -> Any:
    """true/false/on/off → bool；纯数字 → int/float；其余 → str。"""
    low = raw.strip().lower()
    if low in ("true", "on", "yes"):
        return True
    if low in ("false", "off", "no"):
        return False
    try:
        return int(raw)
    except ValueError:
        try:
            return float(raw)
        except ValueError:
            return raw


def _opt_value(args: list[str], flag: str) -> str | None:
    """取 ``--flag <value>`` 的值；缺值则报错。"""
    if flag not in args:
        return None
    idx = args.index(flag)
    if idx + 1 >= len(args):
        raise MilocoLiteError(f"{flag} 需要一个参数值")
    return args[idx + 1]


# ── 命令 ────────────────────────────────────────────────────────────────────
def cmd_login(args: list[str]) -> int:
    device_id = load_or_make_device_id()
    url = oauth.gen_auth_url(device_id)
    if "--url-only" in args:
        _out({"oauth_url": url})
        return 0
    print("\n请在浏览器打开以下链接完成小米账号授权：\n")
    print(f"  {url}\n")
    print("授权后回调页会显示一段 base64 授权码，复制它。")
    print("然后运行: miloco-lite authorize <授权码>\n")
    return 0


def cmd_authorize(args: list[str]) -> int:
    if not args:
        raise MilocoLiteError("用法: miloco-lite authorize <base64授权码>")
    device_id = load_or_make_device_id()
    code, state = oauth.parse_auth_payload(args[0])
    if state != state_of(device_id):
        raise MilocoLiteError("state 不匹配，请用本机 login 生成的链接重新授权")
    tok = oauth.exchange_code(device_id, code)
    save_token(tok)
    info = MiHomeClient(tok["access_token"]).user_info()
    _out({"status": "ok", "message": "登录成功", "user": info})
    return 0


def cmd_status(args: list[str]) -> int:
    tok = load_token()
    if not tok:
        _out({"is_bound": False})
        return 0
    try:
        info = get_client().user_info()
        _out({"is_bound": True, "user": info, "expires_ts": tok.get("expires_ts")})
    except MilocoLiteError as e:
        _out({"is_bound": True, "valid": False, "error": str(e)})
    return 0


def cmd_devices(args: list[str]) -> int:
    room = _opt_value(args, "--room")
    only_online = "--online" in args
    print("# did|name|room|model|online")
    for d in build_device_list():
        if room and d["room"] != room:
            continue
        if only_online and not d["online"]:
            continue
        print(f"{d['did']}|{d['name']}|{d['room']}|{d['model']}|"
              f"{'online' if d['online'] else 'offline'}")
    return 0


def cmd_spec(args: list[str]) -> int:
    if not args:
        raise MilocoLiteError("用法: spec <did> [--json]")
    did = args[0]
    urn, info = spec.urn_of_did(did)
    parsed = spec.parse(spec.fetch_instance(urn))
    if "--json" in args:
        _out({"did": did, "name": info["name"], "room": info["room"], **parsed})
        return 0
    print(f"did={did}  name={info['name']}  room={info['room']}  "
          f"online={'online' if info['online'] else 'offline'}")
    print(f"urn={urn}")
    print("\n# access: wr=读写 / r=只读 / w=只写 / x=动作")
    print(f"\nproperties ({len(parsed['properties'])}):")
    for p in parsed["properties"]:
        line = f"  {p['iid']}  {p['name']}|{p['access']}|{p['format']}"
        if p["constraint"]:
            line += f"|{p['constraint']}"
        if p["unit"]:
            line += f"|{p['unit']}"
        print(line)
    if parsed["actions"]:
        print(f"\nactions ({len(parsed['actions'])}):")
        for a in parsed["actions"]:
            print(f"  {a['iid']}  {a['name']}|x|in={a['in']}")
    return 0


def cmd_props(args: list[str]) -> int:
    if len(args) < 2:
        raise MilocoLiteError("用法: props <did> <siid.piid> [<siid.piid> ...]")
    did, iids = args[0], args[1:]
    cli = get_client()
    params = []
    for iid in iids:
        s, p = _parse_iid(iid)
        params.append({"did": did, "siid": s, "piid": p})
    _out(cli.get_props(params))
    return 0


def cmd_control(args: list[str]) -> int:
    if len(args) < 3 or (len(args) - 1) % 2 != 0:
        raise MilocoLiteError("用法: control <did> <siid.piid> <value> [<siid.piid> <value> ...]")
    did, rest = args[0], args[1:]
    cli = get_client()
    params = []
    for i in range(0, len(rest), 2):
        s, p = _parse_iid(rest[i])
        params.append({"did": did, "siid": s, "piid": p, "value": _infer_value(rest[i + 1])})
    _out(cli.set_props(params))
    return 0


def cmd_action(args: list[str]) -> int:
    if len(args) < 2:
        raise MilocoLiteError("用法: action <did> <siid.aiid> [in值 ...]")
    did = args[0]
    s, a = _parse_iid(args[1])
    in_list = [_infer_value(v) for v in args[2:]]
    _out(get_client().action({"did": did, "siid": s, "aiid": a, "in": in_list}))
    return 0


_COMMANDS = {
    "login": cmd_login, "authorize": cmd_authorize, "status": cmd_status,
    "devices": cmd_devices, "spec": cmd_spec, "props": cmd_props,
    "control": cmd_control, "action": cmd_action,
}

_HELP = """miloco-lite —— 独立小米米家设备 CLI（不依赖后端服务）

命令:
  login [--url-only]                       生成授权链接
  authorize <base64授权码>                 提交授权码完成登录
  status                                   查看登录状态
  devices [--room <房间>] [--online]       列出设备
  spec <did> [--json]                      查看设备支持的属性/动作(含 iid、取值范围)
  props <did> <siid.piid>...               查询设备属性值
  control <did> <siid.piid> <value> [...]  控制设备
  action <did> <siid.aiid> [in...]         调用设备动作

示例:
  miloco-lite login
  miloco-lite authorize eyJjb2Rl...
  miloco-lite devices --online
  miloco-lite spec 1166187070
  miloco-lite control 1166187070 2.1 true 2.2 80
"""


def main() -> int:
    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(_HELP)
        return 0
    cmd, rest = argv[0], argv[1:]
    fn = _COMMANDS.get(cmd)
    if not fn:
        print(f"未知命令: {cmd}\n", file=sys.stderr)
        print(_HELP)
        return 1
    try:
        return fn(rest)
    except MilocoLiteError as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 3
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"error": f"{type(e).__name__}: {e}"}, ensure_ascii=False),
              file=sys.stderr)
        return 3
