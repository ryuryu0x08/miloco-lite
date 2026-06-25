"""OAuth2：拼授权 URL、授权码换 token、refresh_token 刷新。

对应官方 backend/miot/src/miot/cloud.py 的 MIoTOAuth2Client。
端点 GET {host}/app/v2/mico/oauth/get_token?data=<json>，无 client_secret。
"""
from __future__ import annotations

import base64
import json
import time
from urllib.parse import urlencode

import httpx

from .const import (
    API_HOST_DEFAULT,
    OAUTH2_AUTH_URL,
    OAUTH2_CLIENT_ID,
    PROJECT_CODE,
    REDIRECT_URI,
    TOKEN_EXPIRES_RATIO,
)
from .errors import MilocoLiteError
from .store import state_of


def gen_auth_url(device_id: str, skip_confirm: bool = False) -> str:
    """生成小米账号授权 URL。"""
    params = {
        "redirect_uri": REDIRECT_URI,
        "client_id": OAUTH2_CLIENT_ID,
        "response_type": "code",
        "device_id": device_id,
        "state": state_of(device_id),
        "skip_confirm": skip_confirm,
    }
    return f"{OAUTH2_AUTH_URL}?{urlencode(params)}"


def _get_token(data: dict) -> dict:
    """调 oauth/get_token，返回归一化 token 信息。"""
    url = f"https://{API_HOST_DEFAULT}/app/v2/{PROJECT_CODE}/oauth/get_token"
    with httpx.Client(timeout=30) as c:
        r = c.get(
            url,
            params={"data": json.dumps(data)},
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
    if r.status_code != 200:
        raise MilocoLiteError(f"oauth get_token HTTP {r.status_code}: {r.text[:300]}")
    obj = r.json()
    res = obj.get("result") or {}
    if obj.get("code") != 0 or not res.get("access_token") or not res.get("refresh_token"):
        raise MilocoLiteError(f"oauth get_token 业务失败: {r.text[:300]}")
    return {
        "access_token": res["access_token"],
        "refresh_token": res["refresh_token"],
        "expires_ts": int(time.time() + res.get("expires_in", 0) * TOKEN_EXPIRES_RATIO),
    }


def exchange_code(device_id: str, code: str) -> dict:
    """授权码换 token。"""
    return _get_token(
        {
            "client_id": OAUTH2_CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "code": code,
            "device_id": device_id,
        }
    )


def refresh(refresh_tok: str) -> dict:
    """refresh_token 刷新 access_token。"""
    return _get_token(
        {
            "client_id": OAUTH2_CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "refresh_token": refresh_tok,
        }
    )


def parse_auth_payload(payload: str) -> tuple[str, str]:
    """解析回调页给出的 base64({code,state})，返回 (code, state)。"""
    try:
        raw = base64.b64decode(payload.strip()).decode("utf-8")
        data = json.loads(raw)
        code, state = data["code"].strip(), data["state"].strip()
    except (ValueError, KeyError, AttributeError) as e:
        raise MilocoLiteError(f"授权码格式错误，请从回调页直接复制: {e}")
    if not code or not state:
        raise MilocoLiteError("授权码中 code/state 为空")
    return code, state
