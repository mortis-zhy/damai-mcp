# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned
- L4 业务层：猫眼/飞猪抢票
- 滑块验证码识别（OpenCV + ddddocr）
- 录制-回放工作流
- MCP 官方注册表提交

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