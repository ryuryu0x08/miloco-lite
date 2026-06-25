---
name: miloco-lite
description: Use when controlling or querying the user's Xiaomi/Mijia (米家) smart-home devices — lights, fans, AC, plugs, sensors — via the miloco-lite CLI. Triggers include requests like "turn on/off the light", "调亮度/色温", "把空调调到", listing home devices, or reading device state.
---

# miloco-lite

## Overview

`miloco-lite` is a standalone CLI (already on PATH) that controls the user's Xiaomi/Mijia devices directly via Xiaomi cloud — no backend service needed. It covers: login, list devices, query spec, read props, control, action.

**The one rule that matters most: write operations (`control`/`action`) routinely return `code:1` but STILL SUCCEED. Never judge success by the return code — always confirm by reading back with `props`.**

## Standard workflow

Always follow this order — skipping `spec` leads to guessing wrong iids:

1. `miloco-lite devices [--room <房间>] [--online]` — find the target device's `did`
2. `miloco-lite spec <did>` — see which `siid.piid` controls what, and value ranges
3. `miloco-lite props <did> <siid.piid>...` — read current state (baseline)
4. `miloco-lite control <did> <siid.piid> <value> [...]` — change it
5. `miloco-lite props <did> <siid.piid>` — **read back to confirm** (do NOT trust step 4's code)

## Login (first time only)

Check `miloco-lite status` first. If it shows `is_bound: true`, you are already logged in — skip login (token auto-refreshes; `expires_ts` is the Unix expiry). Only do the flow below when `is_bound: false`.

Login is a 3-step OAuth that **needs the user** (browser auth + paste a code):

1. `miloco-lite login` — prints a `account.xiaomi.com/oauth2/authorize?...` URL. Give that URL to the user.
2. User opens it in a browser, logs in with their Xiaomi account, approves. The callback page (`mico.api.mijia.tech/login_redirect`) then shows a **base64 authorization code**. Ask the user to copy and paste it back to you.
3. `miloco-lite authorize <that base64 code>` — completes login.

**Do NOT run `login --help` or `authorize --help`.** These subcommands have no separate help: `login --help` triggers a real login, `authorize --help` tries to decode `--help` as a code and errors. For flags use the top-level `miloco-lite --help` only.

If the machine has no browser / restricted network, the user must open the URL on another device; the code is just text they paste back — it does not need to reach this machine.

## Quick reference

| Command | Purpose |
|---|---|
| `login` / `authorize <code>` / `status` | OAuth login (once); token auto-refreshes |
| `devices [--room X] [--online]` | list devices: `did\|name\|room\|model\|online` |
| `spec <did> [--json]` | list properties/actions with iid + ranges |
| `props <did> <siid.piid>...` | read property values |
| `control <did> <siid.piid> <value> [...]` | set one or many properties |
| `action <did> <siid.aiid> [in...]` | invoke an action (e.g. toggle) |

Value types: `true/false/on/off` → bool; bare number → number; enum → the number from spec (e.g. mode `Night=2` → pass `2`).

## Reading spec output

```
properties (32):
  2.1   on|wr|bool                                  # 灯开关
  2.2   brightness|wr|uint16|[1,100;1]|percentage   # 亮度 1-100
  2.3   color-temperature|wr|uint32|[2700,6500;1]   # 色温
  11.1  on|wr|bool                                  # 风扇开关
  11.2  fan-level|wr|uint8|Level1=1,...,Auto=255     # 风扇档位
```

- Line head `2.1` is the `siid.piid` you pass to control/props.
- `wr`=read+write (controllable), `r`=read-only.
- `[1,100;1]` = min,max,step. `Night=2` = enum, pass the number.
- **Different functions live under different service numbers.** A "灯风扇二合一" device puts light on service `2` (`2.1` on, `2.2` brightness) and fan on service `11` (`11.1` on, `11.2` level). Multiple `on` entries (`2.1`/`11.1`/`12.1`) are different sub-circuits — match by the service number, never guess. Touch only the service the user asked about.
- In `props` output, the `iid` field looks like `0.2.2`; the leading `0` is just a response prefix — the meaningful part is `siid.piid` (`2.2`).

## Critical: write ops return code:1 but succeed

```bash
miloco-lite control 1166187070 2.2 50
# → {"code": 1, ...}   ← looks like failure, IS NOT

miloco-lite props 1166187070 2.2
# → {"value": 50, "code": 0}   ← THIS confirms success
```

Xiaomi cloud returns an unreliable code for writes (especially light groups `group.xxx`). Confirm success by: value changed to target, read `code:0`, and `updateTime` advanced. Never report success or failure based on the control call's `code`.

## Common mistakes

- ❌ Reporting "failed" because `control` returned `code:1` → always read back with `props`.
- ❌ Guessing iids without `spec` → wrong service/piid, or hitting the fan when meaning the light.
- ❌ Setting multiple devices when the user named one → operate only the requested `did`/service.
- ❌ Re-running `login` when already logged in → check `status` first; token persists and auto-refreshes.

## Notes

- Multi-property in one call: `control <did> 2.1 true 2.2 80 2.3 2700`.
- `spec` works without login (public miot-spec.org); everything else needs login.
- Run `miloco-lite --help` for exact flags.
