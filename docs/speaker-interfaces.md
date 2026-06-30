# 小米 LX06 音箱接口手册

设备 IP：192.168.6.9，SSH root@192.168.6.9（密码 open-xiaoai）

---

## 1. 启动链

```
/etc/rc.local
  └─ /data/init.sh
       ├─ rm -f + touch /tmp/mico_aivs_lab/instruction.log
       └─ /data/open-xiaoai/client ws://192.168.6.2:4399 &   ← 替换此行
```

`/data/` 为 ubifs，持久化，约 125MB 可用。

---

## 2. 麦克风

| 项目 | 值 |
|------|----|
| 硬件设备 | hw:0,3 |
| 独占进程 | mipns-xiaomi（无法夺取） |
| 共享读取 | pcm.Capture（dsnoop，已配置） |
| 格式 | 48000Hz S32_LE 4ch |

`/etc/asound.conf` 中已配置 dsnoop，Sherpa-ONNX 可直接读 `pcm.Capture`。

---

## 3. ASR（语音识别）

### 触发

```sh
ubus call pnshelper event_notify '{"src":1,"event":0}'
# 返回 {"code":0} 表示成功
```

触发后音箱开始录音，VAD 检测到说话结束后自动上传小米云 ASR。

### 结果读取

结果写入 `/tmp/mico_aivs_lab/instruction.log`（JSON Lines，重启清空）。

取 `is_final==true` + `namespace=="SpeechRecognizer"` + `name=="RecognizeResult"` 的行：

```json
{
  "header": {
    "dialog_id": "464bdc98...",
    "name": "RecognizeResult",
    "namespace": "SpeechRecognizer"
  },
  "payload": {
    "is_final": true,
    "is_vad_begin": true,
    "results": [{"text": "识别文本", "origin_text": "识别文本"}]
  }
}
```

关键字段：
- `payload.is_final`：true 表示最终结果
- `payload.is_vad_begin`：false 表示没有检测到说话（text 为空）
- `payload.results[0].text`：识别文本
- `header.dialog_id`：同一对话共享，可用于去重

### 超时行为（已验证）

触发后**不说话**，约 5 秒后小米 ASR 自动写入：

```json
{"payload":{"is_final":true,"results":[{"text":"","origin_text":""}]}}
```

即 `is_final==true` + `is_vad_begin==false` + `text==""` 。

**结论**：tail 轮询等 `is_final==true` 一定会退出，无需主动停止 ASR。ctx timeout 仅作极端情况兜底（小米云挂掉等）。

---

## 4. 播放

### miplayer（推荐，支持 HTTP URL）

```sh
miplayer --file http://192.168.6.2:8080/audio/xxx.mp3
# 支持 mp3、opus 等格式（内置 libffmpeg + libvlc）
# 阻塞直到播放结束
```

参数说明：
- `--file`：文件路径或 HTTP URL
- `--socket`：Unix socket，接收 URL 字符串（不是裸 PCM）
- `--loop`：循环播放

### aplay（备选，裸 PCM）

```sh
aplay -D dmixer -f S16_LE -r 48000 -c 2 /tmp/audio.pcm
```

`dmixer` 设备：hw:0,2，48000Hz S16_LE stereo。

---

## 5. LED 控制

### ubus 接口

```sh
# 开启效果
ubus call led show '{"L":<值>,"pos":0}'

# 关闭（建议 L=0..8 全部 shut）
ubus call led shut '{"L":<值>}'

# 查当前状态
ubus call led status
```

### L 值效果对照表

| L | 效果 | 建议用途 |
|---|------|----------|
| 1 | 从中间向两侧展开，播放一次 | 唤醒词触发 |
| 2 | 光条左右循环移动 | LLM 思考中 |
| 3 | 中间光条静止（原生响应音量大小） | 收音/监听中 |
| 4 | 整条白色呼吸 | TTS 播放中 |
| 5 | 彩色光带颜色滚动 | 音乐播放 |
| 6 | 橙色呼吸 | 错误/警告 |
| 7 | 紫色常亮 | 待定 |
| 8+ | 无效果 | — |

硬件：AW21036，12 颗 RGB LED，I2C 地址 2-0034。

---

## 6. ubus 可用对象（完整列表）

```
ai_crontab    alarm         ir_agent      led
mdplay        mediaplayer   messagingagent mibluealsa
mibrain       mibt          mibt_mesh     mic_audio
miio          miplay        nightmode     notify
path_child_mode pnshelper   qplayer       service
sound_effect  system        ultrasense    usb_audio
voice_print   voip
```

### pnshelper（ASR 触发）

```sh
ubus call pnshelper event_notify '{"src":1,"event":0}'
```

### mic_audio

```sh
ubus -v list mic_audio
# ledd 内部会调用：
ubus call mic_audio set_event '{"event":1,"value":2}'
ubus call mic_audio set_event '{"event":1,"value":1}'
```

---

## 7. 存储

| 路径 | 类型 | 说明 |
|------|------|------|
| /data/ | ubifs，持久 | 125MB 可用，部署二进制用 |
| /tmp/ | tmpfs，重启清空 | instruction.log 在此 |
| /etc/asound.conf | 持久 | ALSA 配置 |
| /data/init.sh | 持久 | 开机启动脚本 |

---

## 8. 网络

- 音箱 → NAS 192.168.6.2：内网直连，延迟约 3ms
- 出站 TCP 无限制
- 无 Python，无 bash（只有 busybox ash），有 strace、nc（TCP only）
