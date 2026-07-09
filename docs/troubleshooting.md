# 故障排查

## `adb` 找不到

```
ADBError: adb 未找到。请安装 Android Platform Tools ...
```

**解决**：
1. 安装 [Android Platform Tools](https://developer.android.com/studio/releases/platform-tools)，把 `adb.exe` 加入 PATH
2. 或用模拟器自带的 adb：
   - 雷电：`C:\Program Files\LDPlayer\adb.exe`
   - MuMu：`C:\Program Files\MuMu\adb.exe`
   - 夜神：`C:\Program Files\Nox\bin\nox_adb.exe`

`damai-mcp` 会自动检测这些位置。

## 设备 offline / unauthorized

```
DeviceNotFoundError: 设备未连接: 127.0.0.1:5555
```

**雷电模拟器**：设置 → 其他设置 → 开启 `ADB 调试`
**MuMu 模拟器**：默认 7555 端口
**真机**：USB 连接后开启 `开发者选项 → USB 调试`，手机弹出"是否允许调试"选"允许"

## UI 元素找不到

```
UIElementNotFoundError: 等待 text='立即购买' 超时（5.0s，dump 节点数 234）
```

**原因**：大麦改版导致选择器失效。

**解决**：
```bash
python examples/probe_selectors.py --device 127.0.0.1:5555
```
输出所有可点击元素，更新 `src/damai_mcp/damai/selectors.py` 里的 `DamaiSelectors`。

## 中文输入无效

`input_text` 默认调用 `adb shell input text`，只支持 ASCII。

**解决**：装 [ADBKeyBoard](https://github.com/senzhk/ADBKeyBoard)：
```bash
adb install ADBKeyBoard.apk
adb shell ime enable com.android.adbkeyboard/.AdbIME
adb shell ime set com.android.adbkeyboard/.AdbIME
```

之后用 `adb shell am broadcast -a ADB_INPUT_TEXT --es msg "中文"` 即可。

## 中文找元素超时

`uiautomator dump` 对某些大麦 UI 节点的 `text` 属性返回的是 Unicode 转义后的乱码。

**解决**：用 `find_text` 的 `exact=False` 子串匹配，或 `find_resource_id`。

## 抢票时截图看到滑块验证码

大麦对单设备高频点击会触发滑块。本项目**未实现自动滑块识别**。

**临时方案**：
1. 手动在模拟器里过滑块
2. 增加多设备分散请求
3. 接入 [打码平台](https://github.com/sml2h3/ddddocr)（TODO）

## MCP server 启动失败

```
ModuleNotFoundError: No module named 'damai_mcp'
```

**解决**：用 `pip install -e .` 在仓库根目录安装，或 `pip install damai-mcp` 从 PyPI 装。

## 性能调优

`damai_grab` 内部 poll UI 用 150ms 间隔。要更激进：

```python
from damai_mcp.damai.actions import damai_grab
# 通过修改源码里 poll_interval_ms，或干脆自己用 L3 工具组合
```

---

## 调试技巧

1. **截图前置**：每个 MCP 工具出错都会自动截图到 `./damai_shots/`
2. **UI XML dump**：`dump_ui(save_to="debug.xml")` 把原始 XML 落盘
3. **日志**：`--log-level DEBUG` 看到所有 adb 命令的耗时

```bash
damai-mcp serve --log-level DEBUG --log-dir ./logs
```