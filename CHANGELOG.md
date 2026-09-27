# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned
- 滑块验证码识别（OpenCV + ddddocr）
- 录制-回放工作流
- MCP 官方注册表提交

## [0.2.0] - 2026-07-23

### Added
- **多 App profile 框架**：`app.profile.AppProfile` / `Step` + `app.runner.run_profile()`
- **3 个内置 profile**：damai / maoyan / fliggy（`list-profiles` / `app-grab`）
- **`damai_checklist_grab` 端到端 orchestration**：NTP → login → preheat → countdown → fire
- **NTP 时间同步**：`utils.ntp.async_query` + `ntp_sync` 工具
- **速度优化 1: UI cache**（`utils.ui_cache.UICache`，5-10× 加速）
- **速度优化 2: preheat_warm_dump**（`asyncio.gather` × 3 预热 UI dump + screenshot）
- **速度优化 3: adb batch input**（`actions.batch.batch_tap/swipe/send`，~3× 加速）
- **`utils.find_helpers.search_elements`**（pure-function 搜索 + xpath 支持）
- **CLI 子命令**：`grab`, `list-profiles`, `app-grab`, `ntp-sync`
- **进度回调** `on_phase` / `on_progress` 让上层能看到每个阶段
- **测试**：69+ 单元测试，覆盖 profile / NTP / checklist / optimization

### Changed
- 所有 CLI 输出 ASCII-only（Windows GBK 兼容）
- `damai_checklist.parse_open_time` 支持 `"now"` / `"立即"` / ISO 时区

### Notes
- PyPI v0.2.0 已发布：`pip install damai-mcp`

## [0.1.0] - 2026-07-09

### Added
- L1 设备管理：list_devices, connect, disconnect, device_info
- L2 原子操作：tap, double_tap, long_press, swipe, input_text, press_key, scroll, screenshot
- L3 语义操作：dump_ui, find_by_text/resource_id/xpath, wait_for_text, wait_for_element
- L4 大麦业务：damai_login_check, damai_open_concert, damai_select_price, damai_select_viewer, damai_grab
- FastMCP server 注册全部工具
- CLI 启动脚本 `damai-mcp serve`
- 完整 README + 文档
- pytest 测试覆盖核心逻辑