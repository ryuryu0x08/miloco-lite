"""米家云设备 API 客户端（带加密层）。

对应官方 backend/miot/src/miot/cloud.py 的 MIoTHttpClient。
加密：每实例随机 16B AES key → RSA 公钥加密放 X-Client-Secret 头；
请求体 AES-CBC（IV 复用 key）加密，响应同法解密。
"""
from __future__ import annotations

import base64
import json
import os

import httpx
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding as sym_padding
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.serialization import load_pem_public_key

from .const import (
    API_HOST_DEFAULT,
    API_PUBKEY,
    OAUTH2_CLIENT_ID,
    USER_AGENT,
    X_CLIENT_BIZID,
    X_ENCRYPT_TYPE,
)
from .errors import MilocoLiteError


class MiHomeClient:
    """直连米家云的设备 API 客户端。"""

    def __init__(self, access_token: str):
        self._token = access_token
        self._base = f"https://{API_HOST_DEFAULT}"
        # CBC 的 IV 复用 AES key —— 与官方实现一致，不可改
        self._aes_key = os.urandom(16)
        self._cipher = Cipher(
            algorithms.AES(self._aes_key),
            modes.CBC(self._aes_key),
            backend=default_backend(),
        )
        pub = load_pem_public_key(API_PUBKEY.encode("utf-8"), default_backend())
        self._client_secret_b64 = base64.b64encode(
            pub.encrypt(self._aes_key, asym_padding.PKCS1v15())
        ).decode("utf-8")

    @property
    def _headers(self) -> dict:
        return {
            "Content-Type": "text/plain",
            "User-Agent": USER_AGENT,
            "X-Client-BizId": X_CLIENT_BIZID,
            "X-Encrypt-Type": X_ENCRYPT_TYPE,
            "X-Client-AppId": OAUTH2_CLIENT_ID,
            "X-Client-Secret": self._client_secret_b64,
            "Host": API_HOST_DEFAULT,
            "Authorization": f"Bearer{self._token}",  # Bearer 后无空格，与官方一致
        }

    def _enc(self, data: dict) -> str:
        enc = self._cipher.encryptor()
        padder = sym_padding.PKCS7(128).padder()
        padded = padder.update(json.dumps(data).encode("utf-8")) + padder.finalize()
        return base64.b64encode(enc.update(padded) + enc.finalize()).decode("utf-8")

    def _dec(self, data: str) -> dict:
        dec = self._cipher.decryptor()
        unpadder = sym_padding.PKCS7(128).unpadder()
        raw = dec.update(base64.b64decode(data)) + dec.finalize()
        return json.loads((unpadder.update(raw) + unpadder.finalize()).decode("utf-8"))

    def post(self, path: str, data: dict, timeout: int = 30) -> dict:
        with httpx.Client(timeout=timeout) as c:
            r = c.post(f"{self._base}{path}", content=self._enc(data), headers=self._headers)
        if r.status_code == 401:
            raise MilocoLiteError("access_token 失效(401)，请重新登录")
        if r.status_code != 200:
            raise MilocoLiteError(f"{path} HTTP {r.status_code}: {r.text[:200]}")
        obj = self._dec(r.text)
        if obj.get("code") != 0:
            raise MilocoLiteError(
                f"{path} 业务失败 code={obj.get('code')}: {obj.get('message', '')}"
            )
        return obj

    # ── 各业务接口 ────────────────────────────────────────────────────────
    def user_info(self) -> dict:
        """获取登录用户信息（验证登录态）。"""
        with httpx.Client(timeout=30) as c:
            r = c.get(
                "https://open.account.xiaomi.com/user/profile",
                params={"clientId": OAUTH2_CLIENT_ID, "token": self._token},
                headers={"content-type": "application/x-www-form-urlencoded"},
            )
        obj = r.json()
        d = obj.get("data") or {}
        if obj.get("code") != 0 or "unionId" not in d:
            raise MilocoLiteError(f"获取用户信息失败: {r.text[:200]}")
        return {
            "union_id": d["unionId"],
            "nickname": d.get("miliaoNick", ""),
            "icon": d.get("miliaoIcon", ""),
        }

    def get_homes(self) -> dict:
        """家庭+房间列表（含每个 home/room 的 did 列表）。"""
        return self.post(
            "/app/v2/homeroom/gethome",
            {"limit": 150, "fetch_share": False, "fetch_share_dev": False,
             "plat_form": 0, "app_ver": 9},
        )["result"]

    def device_list_page(self, dids: list[str], start_did: str | None = None) -> dict:
        """按 did 批量拉设备详情（单页）。"""
        data: dict = {"limit": 200, "get_split_device": True, "dids": dids}
        if start_did:
            data["start_did"] = start_did
        return self.post("/app/v2/home/device_list_page", data)["result"]

    def get_props(self, params: list[dict]) -> list:
        """查询属性。params=[{did,siid,piid}, ...]"""
        return self.post(
            "/app/v2/miotspec/prop/get", {"datasource": 1, "params": params}
        )["result"]

    def set_props(self, params: list[dict]) -> list:
        """设置属性。params=[{did,siid,piid,value}, ...]"""
        return self.post(
            "/app/v2/miotspec/prop/set", {"params": params}, timeout=15
        )["result"]

    def action(self, param: dict) -> dict:
        """调用动作。param={did,siid,aiid,in}"""
        return self.post(
            "/app/v2/miotspec/action", {"params": param}, timeout=15
        )["result"]
