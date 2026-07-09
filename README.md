# 🎫 damai-mcp

[![PyPI](https://img.shields.io/badge/pypi-v0.1.0-blue)](https://pypi.org/project/damai-mcp/)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)]()
[![License](https://img.shields.io/badge/license-MIT-yellow)]()
[![MCP](https://img.shields.io/badge/MCP-1.0%2B-purple)](https://modelcontextprotocol.io)

> Android 设备自动化 MCP — 让你的 AI 直接操控手机/模拟器抢大麦 / 猫眼 / 飞猪门票。

大热门场次（¥921 + 0.5 秒开抢）下，**手动抢等于送人头**。本项目用 [Model Context Protocol](https://modelcontextprotocol.io) 把 ADB 操作封装成 30+ 个工具，让 Claude Code / Cursor / 自定义 Agent 都能像人一样操作大麦 APP，关键路径比手快 200~500 ms。

---

## ✨ 核心特性

| | |
|---|---|
| 🪜 **4 层架构** | L1 设备管理 / L2 原子操作 / L3 语义查询 / L4 业务编排 |
| 🚀 **零依赖额外二进制** | 复用本地 `adb`（雷电 / MuMu / SDK 都自带） |
| 🔌 **标准 MCP 协议** | 直接接入 Claude Code / Cursor / Cline / Continue |
| 🧠 **大麦专属** | `damai_grab()` 一行调用完成"等开票 → 抢档 → 选人 → 提交" |
| 📸 **自动截图归档** | 失败时自动存 `damai_shots/` 便于复盘 |
| ⏱️ **毫秒级等待** | 内部用 `asyncio` 高精度 sleep，不浪费开票瞬间 |

---

## 🚀 30 秒上手

### 1. 安装

```bash
pip install damai-mcp
```

### 2. 准备设备（任选其一）

| 设备类型 | ADB 端口 | 优点 |
|---|---|---|
| 雷电模拟器 9 | 127.0.0.1:5555 | 稳定、可多开、免费 |
| MuMu 模拟器 | 127.0.0.1:7555 | 性能好 |
| 真机（USB） | 自动检测 | 最真实 |

启动后确保大麦 APP 已装好并扫码登录。

### 3. 验证连接

```bash
damai-mcp list-devices
# adb: C:\Program Files\LDPlayer\adb.exe
#   127.0.0.1:5555  device  HUAWEI Pura 70 Pro  1080x2400  EMU
```

### 4. 启动 MCP server（给 Claude Code / Cursor 用）

```bash
damai-mcp serve
```

然后在 Claude Code 的 `~/.claude/settings.json` 加入：

```json
{
  "mcpServers": {
    "damai": {
      "command": "damai-mcp",
      "args": ["serve"]
    }
  }
}
```

重启 Claude Code，对话框就能看到 30+ 个 `damai__*` 工具。

### 5. 一句话让 AI 帮你抢

> "用 127.0.0.1:5555 这台设备帮我抢 item 1063631004645，第二档，杨安琪的票，17:21 开票"

AI 会自动串联：

```
list_devices  →  damai_check_login  →  damai_open_concert
   ↓ 等待开票
damai_grab    →  失败截图存到 damai_shots/grab_fail_xxx.png
```

---

## 📐 架构（4 层工具）

```
┌─────────────────────────────────────────────────────────┐
│  L4 业务编排  damai_grab, damai_grab_multi, damai_pay   │  ← AI 直接用
├─────────────────────────────────────────────────────────┤
│  L3 语义查询  find_text, find_resource_id, find_xpath,  │  ← 用语义操作
│              wait_for_element, dump_ui                  │     UI 而不是坐标
├─────────────────────────────────────────────────────────┤
│  L2 原子操作  tap, swipe, input_text, press_key,         │  ← 调试时用
│              screenshot, scroll, long_press             │
├─────────────────────────────────────────────────────────┤
│  L1 设备管理  list_devices, connect_device,             │  ← 一切的开端
│              device_info, disconnect_device             │
└─────────────────────────────────────────────────────────┘
```

**核心原则**：AI 应该用 L3 语义工具，而不是 L2 坐标工具。大麦改版时坐标会失效，但"立即购买"这 4 个字永远在那里。

---

## 🛠️ 直接调用（不用 MCP）

```python
import asyncio
from damai_mcp.damai.actions import damai_grab

async def main():
    result = await damai_grab(
        device_id="127.0.0.1:5555",
        item_id="1063631004645",
        price_index=2,
        viewer_names=["杨安琪"],
        open_time="2026-07-09 17:21:00",
        preheat_seconds=30,
    )
    print(result)

asyncio.run(main())
```

或者命令行：

```bash
python examples/grab_one_ticket.py \
    --device 127.0.0.1:5555 \
    --item 1063631004645 \
    --price 2 \
    --viewer "杨安琪" \
    --open "2026-07-09 17:21:00"
```

---

## 🧰 实战示例

### 抢一张票（单设备）

参见 [`examples/grab_one_ticket.py`](examples/grab_one_ticket.py)。

### 多账号并发（5 个模拟器）

```bash
python examples/multi_devices.py \
    --item 1063631004645 \
    --price 2 \
    --devices 127.0.0.1:5555 127.0.0.1:5557 127.0.0.1:5559 \
    --viewers 杨安琪 张三 李四 \
    --open "2026-07-09 17:21:00"
```

### 当大麦改版时更新选择器

```bash
python examples/probe_selectors.py --device 127.0.0.1:5555
# 输出所有可点击元素，更新 damai_mcp/damai/selectors.py
```

---

## 🧪 开发

```bash
git clone https://github.com/your-org/damai-mcp
cd damai-mcp
pip install -e ".[dev]"

# 测试（不需要真机/模拟器）
pytest

# Lint + 类型检查
ruff check src tests
mypy src

# 跑 example
python examples/grab_one_ticket.py --device 127.0.0.1:5555 --item TEST
```

---

## ⚠️ 合规与免责

本项目仅供**学习与研究自动化测试技术**。请遵守：

1. 大麦 / 猫眼 / 飞猪的用户协议
2. 中国《反不正当竞争法》《消费者权益保护法》等法规
3. 抢到的票请在订单生成后 15 分钟内手动完成支付

作者不对因使用本项目造成的任何账号封禁、法律纠纷或经济损失负责。

---

## 🤝 贡献

欢迎 PR！特别是：

- 猫眼 / 飞猪的 L4 业务封装（目前只实现了大麦）
- 滑块验证码自动识别（OpenCV / ddddocr / 打码平台）
- 录制-回放工作流（让你能"录一遍下次自动跑"）
- 新模拟器适配（夜神 / 逍遥 / BlueStacks）

---

## 📜 License

MIT — see [LICENSE](LICENSE).