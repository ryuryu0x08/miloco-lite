"""协议常量。

全部来自 xiaomi-miloco 仓库 backend/miot/src/miot/const.py，均为公开值，
不含任何 client_secret。提取这些是 lite 版能独立工作的前提。
"""
from __future__ import annotations

PROJECT_CODE = "mico"

# Xiaomi OAuth2（client_id 为该项目在小米侧注册的公开应用 ID）
OAUTH2_CLIENT_ID = "2882303761520431603"
OAUTH2_AUTH_URL = "https://account.xiaomi.com/oauth2/authorize"

# 米家云 API host（cn 区）。换区时为 f"{server}.{API_HOST_DEFAULT}"
API_HOST_DEFAULT = f"{PROJECT_CODE}.api.mijia.tech"

# OAuth 回调地址：固定为小米侧注册值。lite 不真正监听它——授权码由回调页
# 显示给用户手动复制，换 token 时仅作为必须匹配的参数透传。
REDIRECT_URI = f"https://{PROJECT_CODE}.api.mijia.tech/login_redirect"

# 设备 API 请求头固定值
USER_AGENT = f"{PROJECT_CODE}/docker"
X_CLIENT_BIZID = f"{PROJECT_CODE}api"
X_ENCRYPT_TYPE = "1"

# access_token 实际可用时长按 expires_in 打折，提前刷新留余量
TOKEN_EXPIRES_RATIO = 0.7

# 设备 API 加密用的 RSA 公钥：客户端随机生成 AES key，用它加密后放 X-Client-Secret 头
API_PUBKEY = (
    "-----BEGIN PUBLIC KEY-----"
    "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAzH220YGgZOlXJ4eSleFb"
    "Beylq4qHsVNzhPTUTy/caDb4a3GzqH6SX4GiYRilZZZrjjU2ckkr8GM66muaIuJw"
    "r8ZB9SSY3Hqwo32tPowpyxobTN1brmqGK146X6JcFWK/QiUYVXZlcHZuMgXLlWyn"
    "zTMVl2fq7wPbzZwOYFxnSRh8YEnXz6edHAqJqLEqZMP00bNFBGP+yc9xmc7ySSyw"
    "OgW/muVzfD09P2iWhl3x8N+fBBWpuI5HjvyQuiX8CZg3xpEeCV8weaprxMxR0epM"
    "3l7T6rJuPXR1D7yhHaEQj2+dyrZTeJO8D8SnOgzV5j4bp1dTunlzBXGYVjqDsRhZ"
    "qQIDAQAB"
    "-----END PUBLIC KEY-----"
)

# miot-spec.org 公开 spec 接口（免授权）
SPEC_INSTANCE_URL = "https://miot-spec.org/miot-spec-v2/instance"
