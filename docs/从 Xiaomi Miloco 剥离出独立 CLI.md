---
title: "从 Xiaomi Miloco 剥离出独立 CLI：提取全部设备能力的完整过程"
date: 2026-06-26T00:30:00+08:00
description: "把小米开源全屋智能方案 xiaomi-miloco 里与小米云通信的部分整体剥离出来，做成一个不依赖后端、不依赖 WSL、不依赖 MiMo 的独立 CLI。本文按能力逐个拆解：OAuth 登录、查家庭/设备、查 spec 规格、读属性、控属性、调动作——每一项在源码里对应哪段、有什么坑、如何在脱离后端的前提下复现。"
tags: ["Miloco", "小米", "IoT", "Xiaomi", "逆向", "OAuth"]
author: ["六六RyuRyu"]
showToc: true
TocOpen: true
draft: false
hidemeta: false
comments: false
canonicalURL: "https://canonical.url/to/page"
disableHLJS: false
disableShare: false
hideSummary: false
searchHidden: true
ShowReadingTime: true
ShowBreadCrumbs: true
ShowPostNavLinks: true
ShowWordCount: true
ShowRssButtonInSectionTermList: true
UseHugoToc: true
---

# 从 Xiaomi Miloco 剥离出独立 CLI：提取全部设备能力的完整过程

## 结论速览

[xiaomi-miloco](https://github.com/XiaoMi/xiaomi-miloco) 是小米开源的全屋智能 AI 方案，架构是「常驻 FastAPI 后端 + 薄 CLI 客户端 + MiMo 大模型」。我只想要其中「查设备 / 控设备」的能力，不想养一个常驻后端（Windows 上还得装进 WSL）。

于是把后端里真正跟小米云通信的那一小段整体提取出来，做成一个独立 CLI（miloco-lite），**7 个模块约 500 行，依赖只有 httpx + cryptography**。提取覆盖了全部六类能力：

| 能力 | 源码出处 | 能否脱离后端 |
|---|---|---|
| OAuth 登录 | `backend/miot/cloud.py` `MIoTOAuth2Client` | ✅ 无 secret、无需公网回调 |
| 查家庭/设备 | `cloud.py` `gethome` + `device_list_page` | ✅ 无状态 HTTP |
| 查 spec 规格 | `miot-spec.org` 公开接口 | ✅ 免授权 |
| 读属性 | `cloud.py` `miotspec/prop/get` | ✅ |
| 控属性 | `cloud.py` `miotspec/prop/set` | ✅ |
| 调动作 | `cloud.py` `miotspec/action` | ✅ |

全部六类都能脱离后端独立跑。难点不在"逻辑"——逻辑很薄——而在两个隐蔽处：**OAuth 看似需要公网回调（其实不用）**，以及**设备 API 有一层 AES+RSA 加密握手（细节错一个就全挂）**。下面逐个能力拆。

## 零、先认清架构：薄客户端 + 重后端

原项目的调用链：

```
miloco-cli (薄客户端) --HTTP--> miloco 后端 (FastAPI :1810) --> 小米云 --> 设备
                                    └─ 感知引擎 / 规则引擎 / 摄像头流 / MQTT / SQLite
```

做提取前必须先回答一个问题：**逻辑到底在 CLI 还是后端？**

摸下来两个事实：

1. **CLI 是 100% 薄客户端**：`cli/src/miloco_cli/` 里没有任何 `import miot`，所有命令都通过 httpx 转发给后端的 `/api/miot/*`。直接删后端，CLI 立刻报 `cannot connect`。
2. **后端里"查/控"逻辑也很薄**：`service.py` 的 `get_miot_device_list`/`control_device` 等方法，本质是无状态地调小米云，底层全靠 `backend/miot` 这个 SDK 包。那些"重"组件（感知、规则、摄像头、MQTT）跟查/控设备完全无关。

所以提取目标锁定为 **`backend/miot/src/miot/cloud.py`**（约 1100 行）里的两个类：`MIoTOAuth2Client`（登录）和 `MIoTHttpClient`（设备 API）。其余 99%（摄像头解码、MQTT、65KB 的 spec 本地化）都不需要。

## 一、登录能力：OAuth 是不是死结？

这是第一个拦路虎。授权 URL 里的 `redirect_uri` 指向小米官方域名 `mico.api.mijia.tech/login_redirect`，直觉上"授权完成后会回调到小米的服务器，我本地拿不到 code"。

读 `cloud.py` 的 OAuth 实现后，三个担心**全部不成立**：

```python
# const.py —— 全是公开常量，没有任何 secret
OAUTH2_CLIENT_ID = "2882303761520431603"

# MIoTOAuth2Client.get_access_token_async —— 用 code 换 token 只要这些
data = {
    "client_id": OAUTH2_CLIENT_ID,
    "redirect_uri": self._redirect_uri,
    "code": code,
    "device_id": self._device_id,          # "mico." + uuid
}
# GET https://mico.api.mijia.tech/app/v2/mico/oauth/get_token?data=<json>
```

关键洞察——**授权码的获取根本不依赖 redirect_uri 回到谁的服务器**：

1. 小米授权页点同意后，302 跳到 `login_redirect`，这个页面**唯一的作用就是把 base64 的 `{code, state}` 显示给用户看**；
2. 用户手动复制这串，粘进 CLI；
3. CLI 解出 code，直接 HTTP 调 `get_token` 换 token——这一步是无状态的。

`redirect_uri` 在换 token 时只是个**必须与授权时一致的字符串参数**，沿用官方常量即可，CLI 根本不需要真去监听那个地址。

- ❌ 不需要 client_secret（这个 OAuth 应用压根没用 secret）
- ❌ 不需要公网回调服务
- ✅ client_id / redirect_uri 都是代码里的公开常量
- ✅ `state = sha1("d=" + device_id)`，device_id 本地自己生成

提取产物：`oauth.py`（拼 URL / 换 token / 刷新）+ `store.py`（device_id 与 token 本地持久化）。token 刷新也走同一个 `get_token` 端点，传 `refresh_token` 即可，CLI 自己定时刷。

## 二、设备 API 的加密层：真正的成败点

查设备/控设备不是普通 HTTP——`MIoTHttpClient` 有一层加密握手。这是整个提取里唯一"硬"的地方，读 `cloud.py` 的 `__init__` 和 `__api_request_headers` 还原出完整机制：

```python
# 1. 每个 client 实例随机生成一把 16 字节 AES key
self._aes_key = os.urandom(16)

# 2. CBC 模式，IV 复用 AES key 本身（反直觉，但官方就这么写，不可改）
self._cipher = Cipher(algorithms.AES(key), modes.CBC(key))

# 3. 用内置 RSA 公钥加密这把 AES key，base64 后放进请求头
self._client_secret_b64 = base64(rsa_pub.encrypt(aes_key, PKCS1v15))
```

每个请求的构造：

- **请求头** `X-Client-Secret` = RSA 加密后的 AES key（让服务端知道用哪把 key 解你的 body）
- **请求体** = `base64(AES-CBC-PKCS7(json))`
- **响应体** = 用同一把 key AES 解密
- **`Authorization: Bearer<token>`** —— 注意 `Bearer` 后**没有空格**

几个魔鬼细节，错一个就整条链路失败，且报错往往是含糊的 401 或解密乱码：

| 细节 | 正确值 | 错了的后果 |
|---|---|---|
| CBC 的 IV | 复用 AES key | 响应解密成乱码 |
| Authorization | `Bearer{token}`（无空格） | 401 |
| Content-Type | `text/plain` | 服务端不认 body |
| X-Encrypt-Type | `"1"` | 服务端不走解密 |

这层还原出来后，所有设备 API 就都通了。它们共用一个加密的 `post()`，只是 path 和 body 不同。提取产物：`client.py` 的 `MiHomeClient`。

## 三、查家庭与设备列表

设备列表要两步，因为小米把"归属关系"和"设备详情"拆成了两个接口：

```python
# ① 家庭+房间，含每个 home/room 的 did 列表
POST /app/v2/homeroom/gethome
# ② 按 did 批量拉设备详情（分页，每页 ≤150）
POST /app/v2/home/device_list_page
```

组装逻辑：先用 ① 建一张 `did → {home, room}` 映射表，再把所有 did 喂给 ② 拿详情，最后把房间名贴回去。device_list_page 返回的 `spec_type` 字段就是设备的 **urn**（后面查 spec 要用），`isOnline`、`model`、`name` 也在这里。

提取产物：`devices.py`，输出扁平列表 `{did, name, room, home, online, model, urn}`。

> 提取时这里踩了个自己的坑：分页循环 + 设备行解析最初写了两遍（主循环一份、`has_more` 翻页一份）。违反 DRY，重构成 `_device_row` + 单循环。

## 四、查 spec 规格：不用提取，直接用公开接口

"这个设备支持哪些属性、什么取值范围"——这是 `spec` 能力。原项目的 `backend/miot/spec.py` 有 **65KB**，做了大量本地化翻译、模板合并、缓存。但那是为了渲染多语言 UI，我们不需要。

读它发现 spec 的真正源头是一个**公开、免授权**的接口：

```
GET https://miot-spec.org/miot-spec-v2/instance?type=<urn>
```

`urn` 就在设备列表的 `spec_type` 里。返回标准 JSON：`services[].properties[]` / `actions[]`，每项带 `iid` / `type`（含名字）/ `format` / `value-list` / `value-range` / `access`。

所以 spec 这块**完全不用搬后端代码**，直接打这个公开接口、提取字段即可。副作用是 `spec` 命令甚至不需要登录。提取产物：`spec.py`，只保留 `fetch_instance` + `parse`，丢掉那 65KB。

解析后的可读输出长这样（一台灯+风扇二合一设备）：

```
properties (32):
  2.1   on|wr|bool                                    # 灯开关
  2.2   brightness|wr|uint16|[1,100;1]|percentage     # 亮度
  2.3   color-temperature|wr|uint32|[2700,6500;1]|kelvin
  2.4   mode|wr|uint8|Day=1,Night=2,Reading=4,...      # 场景模式(枚举)
  11.1  on|wr|bool                                     # 风扇开关
  11.2  fan-level|wr|uint8|Level1=1,...,Auto=255       # 风扇档位
actions (5):
  2.6   brightness-up|x|in=[]
```

读法：行首 `2.1` 是 `siid.piid`，控制时要用；`wr`=可读写；`[1,100;1]`=min,max,步进；`Day=1`=枚举值传数字 1。**不同功能落在不同 service**（service 2 是灯、11 是风扇），这是理解二合一设备的关键。

## 五、读属性 / 控属性 / 调动作

这三个是 miotspec 标准三件套，body 结构高度一致：

```python
# 读：params 是 [{did, siid, piid}, ...]
POST /app/v2/miotspec/prop/get   {"datasource":1, "params":[...]}
# 写：params 多一个 value
POST /app/v2/miotspec/prop/set   {"params":[{did,siid,piid,value}, ...]}
# 动作：单个 param
POST /app/v2/miotspec/action     {"params":{did,siid,aiid,in:[...]}}
```

`set` 支持一次设多个属性，所以"开灯+调亮度+调色温"可以一条命令搞定。提取产物：`client.py` 的 `get_props` / `set_props` / `action`，CLI 层做 `2.1`→`(siid=2,piid=1)` 的解析和 `true/100/暖光` 的类型推断。

### 这里有个一定要知道的服务端行为

实测发现：**写操作（set/action）经常返回 `code:1`（失败），但设备实际已经执行了。** 把客厅灯亮度从 100 调到 30 再调回，每次接口都报 `code:1`，但灯每次都正确响应。

这不是提取的 bug，是米家云对这类聚合/转发设备的返回码本就不可靠。**判断成功要靠 `prop/get` 回读实际值，不能信返回的 code**：

```bash
miloco-lite control <did> 2.2 50
miloco-lite props   <did> 2.2     # value 是 50 就成了
```

## 六、组装成项目

把提取出的零件按"每个文件只做一件事"组织：

```
src/miloco_lite/
  const.py    协议常量(client_id / host / RSA 公钥)，全是公开值
  store.py    本地 device_id + token 持久化(替代后端 SQLite KV)
  oauth.py    授权 URL / code 换 token / 刷新
  client.py   MiHomeClient：加密层 + 设备 API
  spec.py     miot-spec.org 公开接口拉取 + 解析
  devices.py  会话(token 自动刷新) + 设备列表组装
  cli.py      命令行解析与各子命令
```

后端原本用 SQLite 存 token，这里换成本地 `~/.openclaw/miloco-lite/token.json`——这是"去掉常驻服务"的最后一块拼图：token 持久化不再需要数据库。

## 提取前后对比

| 维度 | 原项目 | miloco-lite |
|---|---|---|
| 运行形态 | 常驻 FastAPI 后端 + CLI | 单一 CLI |
| 代码量 | backend/miot 19 文件 + miloco 后端一大套 | 7 模块 ~500 行 |
| 依赖 | fastapi/uvicorn/supervisor/aiohttp… 几十个 | httpx + cryptography |
| token 存储 | SQLite KV | 本地 JSON |
| 平台 | Windows 须装进 WSL（native wheel） | 纯 Python，到处能跑 |
| 能力 | 全屋 AI（感知/规则/摄像头/查控） | 仅查/控设备 |

## 验证

用真实账号端到端验证（客厅"智能调光风扇灯" `shhf.light.sflt11`，灯+风扇二合一），全部六类能力通过：

- ✅ login / authorize：OAuth 换 token + 用户信息（昵称正确）
- ✅ devices：22 台设备全出（加密链路正确）
- ✅ spec：32 属性 + 5 动作
- ✅ props：读到真实开关/亮度/色温
- ✅ control：灯开关/亮度/色温、风扇开关/档位/摆风
- ✅ action：brightness-up（亮度 80→90）

## 要点小结

1. **先分清薄客户端 vs 重后端**：原 CLI 无逻辑，提取的是后端那一小段无状态代理，而非 CLI。
2. **OAuth 不是死结**：redirect_uri 只是换 token 时的匹配参数，授权码靠用户从回调页手动复制，无需公网回调、无需 secret。
3. **加密层是唯一的真难点**：AES 随机 key + RSA 公钥包装 + CBC(IV=key) + `Bearer` 无空格，四个细节错一个就全挂。
4. **spec 用公开接口**：miot-spec.org 免授权，65KB 的本地解析代码完全不用搬。
5. **写操作返回码不可信**：判断成功靠 `props` 回读，不靠 `code`。
6. **token 存本地 JSON** 替代 SQLite，是去掉常驻服务的最后一步。

