# 工具参考

damai-mcp 注册了 30 个 MCP 工具，分为 4 层。

## L1 — 设备管理（4 个）

### `list_devices(refresh=False)`
列出所有连接的 Android 设备/模拟器。

**参数**：
- `refresh` (bool, default=False) — 跳过缓存

**返回**：
```json
{
  "count": 1,
  "devices": [{"device_id": "127.0.0.1:5555", "model": "...", "screen_size": "1080x2400", ...}],
  "adb_path": "C:\\Program Files\\LDPlayer\\adb.exe"
}
```

### `connect_device(host_port)`
通过 TCP 连接远程模拟器。返回设备信息。

**参数**：
- `host_port` (str) — 形如 `"127.0.0.1:5555"`

### `disconnect_device(device_id)`
断开设备。

### `device_info(device_id)`
获取设备详细信息（型号、安卓版本、屏幕分辨率、内存、ABI）。

---

## L2 — 原子操作（9 个）

所有函数都接受 `device_id` 作为第一个参数。

| 工具 | 参数 | 用途 |
|---|---|---|
| `tap(x, y, duration_ms=50)` | 像素坐标 | 点击 |
| `double_tap(x, y, gap_ms=80)` | 像素坐标 | 双击 |
| `long_press(x, y, duration_ms=800)` | 像素坐标 | 长按 |
| `swipe(x1, y1, x2, y2, duration_ms=300)` | 起止坐标 | 拖动 |
| `scroll(direction, distance_ratio, duration_ms)` | up/down/left/right | 整屏滚动 |
| `input_text(text, delay_ms=0)` | 文本 | 输入（中文需 ADBKeyBoard）|
| `press_key(key)` | home/back/enter/... | 按键 |
| `take_screenshot(save_path, return_base64, max_width)` | 路径 | 截图 |

### 坐标 vs. 语义

L2 工具用像素坐标。大麦改版时坐标会失效。**生产代码尽量用 L3 语义工具。**

---

## L3 — 语义查询（6 个）

| 工具 | 用途 |
|---|---|
| `dump_ui(save_to=None)` | 获取当前界面所有 UI 节点 |
| `find_text(text, exact=True, clickable_only, timeout)` | 按文字查找 |
| `find_resource_id(resource_id, exact, timeout)` | 按 Android resource-id 查找 |
| `find_xpath(xpath, timeout)` | 按 XPath 查找 |
| `wait_for_element(selector, timeout)` | 等待元素出现；支持 `text=` / `resource-id=` / `xpath=` 前缀 |
| `assert_text(text, exact, timeout)` | 断言文字出现（不抛异常） |

### `find_xpath` 示例

```
//node[@text='立即购买' and @clickable='true']
//node[contains(@text, '¥') and @clickable='true']
//node[@resource-id='cn.damai:id/btn_buy']
```

---

## L4 — 大麦业务（9 个）

### `damai_check_login(timeout=3.0)`
检查大麦 APP 是否在前台 + 已登录。返回 `{"logged_in": true/false, "foreground": true/false}`。

### `damai_open_concert(item_id)`
打开大麦演出详情页（尝试 scheme deep-link，失败回退 web URL）。
返回 `{"item_id": ..., "loaded": true/false, "elapsed_ms": ...}`。

### `damai_select_price(price_index, timeout=4.0)`
选择第 N 档票。先等待价格表出现，按 Y 坐标排序，取第 N 个 `¥xxx` 元素点击。

### `damai_select_viewers(viewer_names, timeout=4.0)`
勾选观演人。`viewer_names=["杨安琪"]`，最多等 4 秒。

### `damai_confirm_order(timeout=5.0)`
点击「确认订单」按钮。

### `damai_pay(timeout=5.0)`
点击「立即支付」按钮（后续需手动支付）。

### `damai_grab(...)` ⭐
**一站式抢票**。参数：

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `device_id` | str | 必填 | |
| `item_id` | str | 必填 | 大麦 item id |
| `price_index` | int | 1 | 票档序号 (1-based) |
| `viewer_names` | list[str] | `[]` | 观演人 |
| `ticket_num` | int | 1 | 张数 |
| `open_time` | str | `""` | `""`=立即抢，否则 `"YYYY-MM-DD HH:MM:SS"` |
| `preheat_seconds` | float | 30.0 | 开票前多少秒开始预热 |
| `max_runtime_sec` | float | 600.0 | 硬超时 |

返回：
```json
{
  "status": "submitted" | "failed",
  "elapsed_ms": 1234,
  "item_id": "1063631004645",
  "price_index": 2,
  "viewer_names": ["杨安琪"],
  "pay_btn_found": true,
  "screenshots": ["damai_shots/grab_done_xxx.png"],
  "error": null
}
```

### `damai_grab_multi(accounts, item_id, price_index, open_time, preheat_seconds)`
多账号并发抢票。`accounts` 是 list of dict:
```python
[
    {"device_id": "127.0.0.1:5555", "viewer_names": ["杨安琪"], "ticket_num": 1},
    {"device_id": "127.0.0.1:5557", "viewer_names": ["张三"], "ticket_num": 1},
]
```
内部用 `asyncio.gather` 并发，返回每个账号的结果。

---

## 错误码

所有工具捕获异常后转换为结构化错误：

| 异常 | 何时抛 |
|---|---|
| `DeviceNotFoundError` | `adb devices` 找不到指定 device_id |
| `ADBError` | adb 命令返回非 0 |
| `UIElementNotFoundError` | 超时未找到目标元素 |
| `AppNotRunningError` | 大麦未在前台 |
| `DamaiLoginExpiredError` | 大麦未登录 |
| `DamaiGrabFailedError` | 抢票流程失败 |

调用方应该捕获 `DamaiMCPError`（所有异常的基类）。