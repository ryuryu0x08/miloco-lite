# miloco-lite

独立的小米米家设备命令行工具：**登录 + 查设备 + 控制设备**，不依赖 [xiaomi-miloco](https://github.com/XiaoMi/xiaomi-miloco) 的后端服务、感知引擎、规则引擎。

它从官方 `backend/miot` 包里提取出与小米云通信的最小子集，直连米家云 HTTP API。token 存本地，无需常驻后端、无需 WSL、无需 MiMo 模型 key。

> 提取过程与原理见 [docs/从 Xiaomi Miloco 剥离出独立 CLI.md](docs/从%20Xiaomi%20Miloco%20剥离出独立%20CLI.md)。

## 能做什么

| 能力 | 说明 |
|---|---|
| 登录 | 小米账号 OAuth，token 存本地自动刷新 |
| 查设备 | 列出账号下全部米家设备 |
| 查规格 | 查设备支持的属性/动作及取值范围（免登录，走 miot-spec.org） |
| 读状态 | 读设备当前属性值 |
| 控制 | 开关、亮度、色温、风扇档位、模式…… |
| 动作 | 调用设备动作（如 toggle、brightness-up） |

**不支持**（这些需要原项目的后端常驻引擎）：摄像头多模态感知、自动化规则、人脸识别。

## 安装

依赖 [uv](https://github.com/astral-sh/uv)。

```bash
# 安装为全局命令
uv tool install /Users/ryuryu/Documents/xiaomi-miloco-lite

# 或开发模式直接跑
cd xiaomi-miloco-lite && uv run miloco-lite --help
```

## 用法

### 1. 登录（仅一次）

```bash
miloco-lite login
```

打印授权链接 → 浏览器打开 → 小米账号登录授权 → 回调页显示一段 base64 授权码，复制它：

```bash
miloco-lite authorize <粘贴 base64 授权码>
miloco-lite status        # 确认 is_bound: true
```

token 存于 `~/.openclaw/miloco-lite/`，过期自动刷新，无需重复登录。

### 2. 查设备

```bash
miloco-lite devices                 # 全部
miloco-lite devices --room 卧室     # 按房间
miloco-lite devices --online        # 只看在线
```

输出：`did|名称|房间|型号|在线`。记下要操作设备的 `did`。

### 3. 看设备支持哪些操作

```bash
miloco-lite spec <did>
```

```
properties (6):
  2.1  on|wr|bool                                   # 开关
  2.2  brightness|wr|uint16|[1,100;1]|percentage    # 亮度
  2.3  color-temperature|wr|uint32|[2700,6500;1]|kelvin
  11.1 on|wr|bool                                   # 风扇开关
  11.2 fan-level|wr|uint8|Level1=1,...,Auto=255      # 风扇档位
actions (5):
  2.6  brightness-up|x|in=[]
```

读法：行首 `2.1` 是 `siid.piid`（操作要用）；`wr`=可读写；`[1,100;1]`=范围 min,max,步进；`Day=1`=枚举传数字。

### 4. 读当前状态

```bash
miloco-lite props <did> 2.1 2.2     # 读开关、亮度
```

### 5. 控制

```bash
miloco-lite control <did> 2.1 true              # 开
miloco-lite control <did> 2.2 80                # 亮度 80
miloco-lite control <did> 2.1 true 2.2 80 2.3 2700   # 一条命令设多个
miloco-lite control <did> 11.1 true 11.2 2      # 开风扇 + 2 档
```

值：`true/false/on/off` → 布尔；数字直接写；枚举传 spec 给的数字。

### 6. 动作

```bash
miloco-lite action <did> 2.6        # brightness-up
```

## ⚠️ 重要：写操作的返回码不可信

米家云对 `control`/`action` 的写操作**经常返回 `code:1`（失败），但设备实际已执行**。这是服务端行为，非本工具 bug。

**判断是否成功，请用 `props` 回读实际值**，不要看返回的 code：

```bash
miloco-lite control <did> 2.2 50
miloco-lite props   <did> 2.2      # value 是 50 就成功了
```

## 命令一览

```
login [--url-only]                       生成授权链接
authorize <base64授权码>                 完成登录
status                                   登录状态
devices [--room <房间>] [--online]       列设备
spec <did> [--json]                      查规格
props <did> <siid.piid>...               读属性
control <did> <siid.piid> <value> [...]  控制
action <did> <siid.aiid> [in...]         动作
```

退出码：`0` 成功 / `1` 参数错 / `3` 业务或网络错。

## 数据与隐私

- token、device_id 仅存本地 `~/.openclaw/miloco-lite/`
- 直连小米官方 `mico.api.mijia.tech`，不经任何第三方
- 不含任何 client_secret（该 OAuth 应用不需要）
