# 大麦 MCP 抢票项目：技术复盘与可行性终评

> 一份给"未来的自己"的复盘：技术上我们做到了什么、碰到了哪些墙、为什么别人能抢到而我们不能。
> 写于 2026-09-24，距离项目开始约 3 个月。

---

## 0. 项目目标（最初）

做一个 Android 自动化抢票 MCP server，能在指定时间点把大麦 / 猫眼 / 飞猪 App 里的演唱会门票抢下来。

**目标演出**：王俊凯演唱会（热门场次，App 专享）。

**产物**：可发布的 PyPI 包 `damai-mcp` + 一套能跑通的 framework。

---

## 1. 我们做对了什么（技术收益盘点）

### 1.1 framework 本身是完整可用的

| 模块 | 实现 | 状态 |
|---|---|---|
| MCP server（FastMCP + stdio/HTTP） | `src/damai_mcp/server.py` | ✅ |
| adb 抽象层（异步 + 错误重试） | `src/damai_mcp/device/adb.py` | ✅ |
| UI dump → UIElements 解析（lxml） | `src/damai_mcp/inspector/dump.py` | ✅ |
| 元素搜索（按 text / resource-id / content-desc） | `src/damai_mcp/inspector/search.py` | ✅ |
| 点击 / 滑动 / 输入 / 截图 | `src/damai_mcp/actions/*.py` | ✅ |
| 批量 adb input（一次 30 步输入） | `src/damai_mcp/actions/batch.py` | ✅ |
| NTP 时间同步 | `src/damai_mcp/utils/ntp.py` | ✅ |
| UI dump 缓存（2 秒 TTL） | `src/damai_mcp/utils/ui_cache.py` | ✅ |
| 3 个 app profile（damai / maoyan / fliggy） | `src/damai_mcp/app/profile.py` | ✅ |
| 通用 `app_grab` MCP 工具 | `src/damai_mcp/server.py` | ✅ |
| 抢票 checklist（开抢前 1 小时清单） | `examples/pre_grab_checklist.py` | ✅ |
| 3 设备并发沙盒 | `examples/three_apps_sandbox.py` | ✅ |

**测试**：69+ 测试通过。**发布**：PyPI v0.2.3 已上线。

### 1.2 一个被低估的关键修复

`inspector/dump.py` 改用 `adb exec-out cat` 替代 `adb shell cat`：

```python
# 旧写法（被 GBK 编码破坏中文）
adb shell cat /sdcard/window_dump.xml
# 新写法（保留原始字节）
adb exec-out cat /sdcard/window_dump.xml
```

Windows 的 cmd 控制台默认 code page 是 GBK（CP936）。`adb shell cat` 走的是 terminal 管道，Windows 会用 GBK 解码内核输出的字节流，而 `uiautomator dump` 写的是 UTF-8 编码的 XML。中文 UTF-8 字节（`0xE4 0xB8 ...`）被 GBK 强行解码会产生大量 `U+FFFD` 替换字符，搜索中文 text 完全失灵。

切换到 `exec-out` 后，adb 把目标命令的 stdout 当作 raw bytes 直通回来，绕过了 Windows 的字符集转换。这个修复让 framework **第一次能在中文 UI dump 里正确搜索**。

### 1.3 一些工程层面的取舍

- **异步优先**：所有 adb 调用走 `asyncio.create_subprocess_exec`，3 设备并发跑下来总耗时 ≈ 最慢单个。
- **profile 而不是 hardcode**：把每个 app 的"打开 → 同意协议 → 点击演出 → 选座 → 提交"流程写成 JSON profile，业务逻辑和 driver 解耦。
- **batch input 而非多次 shell input**：adb `input tap` 每次有 ~30ms fork 开销，30 个点击从 900ms 降到 ~200ms。

---

## 2. 我们碰到了哪些墙（技术细节）

### 2.1 大麦：APM 类加载崩溃

**现象**：点开大麦 → SplashActivity → 几秒钟后白屏 → logcat 里 `ClassNotFoundException: cn.damai.appinfo.PopcornApplication` → 进程死亡。

**根因**：

大麦 APK 在启动早期会调用一个阿里系 APM（Application Performance Management）SDK 做性能埋点。这个 SDK 用了贾扬清团队（[J2C](https://github.com/jiayy/J2C)）的 Java-to-C 混淆，把关键类的字节码转成 C，再交给 Qindroid 虚拟机（在 native 层模拟执行）。

```
SplashMainActivity.onCreate()
  → LauncherApplication.onCreate()
    → Class.forName("cn.damai.appinfo.PopcornApplication")   ← 死在这里
```

模拟器 LDPlayer 9 是 x86_64 ABI，APK 是 arm64-v8a 编译的。LDPlayer 通过 houdini（ARM → x86 翻译层）让 arm 代码能在 x86 上跑。但 J2C 生成的代码里有**自修改字节码**，dex2oat 在编译这些类时会失败（`NoClassDefFoundError`），运行期 class loader 找不到类，整个启动流程崩盘。

我们尝试过的所有修复：

| 尝试 | 原理 | 结果 |
|---|---|---| 
| 等 5 分钟看是否加载完成 | 也许 APM 在做后台异步初始化 | 没用，启动即崩 |
| 断网启动 | 避免 APM 上传崩溃 | 没用，启动期类加载就崩 |
| Frida Gadget 注入 | 在 class load 前 hook Class.forName | 未成功（注入失败，类已加载） |
| 改 houdini 加速比 | 减少翻译抖动 | 没影响结果 |
| 换 arm64 模拟器 | 避免翻译层 | 找不到稳定可用的 arm64 Android 模拟器 |

### 2.2 猫眼：Yoda 人脸验证

**现象**：打开猫眼 → MovieMainActivity → 几秒后弹出"请完成实名认证" → 调用相机 → 几秒后"验证失败，请重试"。

**根因**：

猫眼登录链路调用的是美团的 [Yoda](https://github.com/Meituan-Dianping/Yoda) 人脸活体检测 SDK。Yoda 不是简单的 2D 人脸识别，它至少做这五件事：

1. **RGB 纹理分析**：真实 CMOS 传感器有 PRNU（Photo-Response Non-Uniformity）噪声指纹，是传感器特有的"水印"。模拟器的"相机"输出的是渲染出来的图，没有 PRNU → 异常。
2. **深度 / 3D 信息**：头部转动时面部各点的视差必须符合 3D 几何。RGB 相机没有深度图，要么没有深度要么是伪造的。
3. **微表情时序**：眨眼时虹膜短暂消失 + 眼皮遮挡时间符合生理学。模拟器无法自然"眨眼"，时序特征异常。
4. **次表面散射（SSS）**：真实皮肤的光反射有 SSS 特征（光穿透表皮后在皮下散射）。屏幕 / 平面图像的反射特性完全不同。
5. **设备指纹**：IMEI、传感器列表、CPU ABI、GPU 渲染器。模拟器的 sensor list 经常是空的，ABI 是 x86_64 → 真机几乎都是 arm64-v8a。

**关键的物理限制**：1-4 是物理层面的硬约束。模拟器输出的是"完美的数字图像"，RGB 相机**天然无法**通过 3D 活体检测。这不是配置问题，是物理定律。

### 2.3 飞猪：WebView 白屏

**现象**：飞猪启动到 `fliggyx.android.unicorn.ActWebviewActivity` → WebView 加载 → 白屏 → 卡住。

**根因**（推测，未深入诊断）：

飞猪本质上是一个"App 壳"，核心业务逻辑在 WebView 里。WebView 白屏通常有四种原因：

1. WebView 内核版本不兼容（Android 9 系统 WebView 是 Chromium 54+）
2. WebView 无法加载远程资源（DNS 解析、代理、证书）
3. 阿里系风控检测到 `ro.build.fingerprint` 含 `aosp_*`，返回空 HTML
4. JavaScript 引擎 crash（v8 / jsc 在 x86 上偶发）

我们没有拉全 logcat 做诊断。最有可能是 **3（风控识别模拟器）**，因为飞猪的 WebView 入口资源是 `https://h5api.m.taobao.com` 这种阿里域。

---

## 3. 为什么别人能用模拟器抢到票（事实核查）

网上充斥"模拟器抢票成功"的内容。仔细分类，**它们是四种完全不同的东西**：

### 3.1 类型 A：专业黄牛（设备群控）

```
50-200 台真机 / 云手机（每台都 root + Magisk + 全面伪装）
+ 成熟的多账号 Cookie 池
+ 动态 IP 代理
+ 行为模拟（点击节奏、滑动曲线模拟人）
+ 持续维护 sign 算法
+ 资金：几十万到上百万
```

这种不是"模拟器抢票"，是**工业化黑产**。他们用真机多开，不是雷电这种单机模拟器。

### 3.2 类型 B：粉丝团代抢（半自动）

```
事先填好身份证 + 收货地址 + 支付密码
+ 开抢瞬间用真手点（脚本只负责等待和点击触发）
+ 蹲回流票（5-25 分钟后有人退票）
```

这种"半自动"本质是**真人操作**，不叫抢票脚本。

### 3.3 类型 C：API 重放派（绕过 UI）

```
mitmproxy 抓大麦 / 猫眼的 HTTP 接口
+ 逆向 sign / token 算法
+ Python 脚本定时重放
+ 毫秒级抢票（不启动 App，绕过所有 UI 层风控）
```

这条路**技术上能走通**，但需要持续逆向。sign 算法每周都在变，黑产团队靠这个吃饭。

### 3.4 类型 D：营销内容

```
CSDN / 知乎上"5 分钟 90% 成功率"的文章
+ 没有真实订单截图
+ 没有时间戳证明
+ 大多是 SEO 营销（流量 = 收入）
+ 互相抄袭同一个项目
```

这些文章**全部是假的**。没有任何证据表明它们真的抢到过票。

### 3.5 我们做不到的根本原因

| 维度 | 我们 | 类型 A（黄牛） | 类型 C（API 派） |
|---|---|---|---|
| 设备 | 1 台 LDPlayer 9 | 50-200 台真机 | 服务器 |
| root | 无 | 全 root | N/A |
| 资金 | 0 | 几十万 | 几万 |
| 反风控 | 无 | 完整系统 | 中等 |
| sign 逆向 | 无 | 持续 | 持续 |

**事实**：我们用 **1 台默认配置模拟器**，期望**稳定抢到热门演出票**——这不是技术挑战问题，是资源配置问题。

---

## 4. 三个 App 的失败原因对比

| App | 失败环节 | 原因类型 | 修复可能性 |
|---|---|---|---|
| 大麦 | APM 类加载崩溃 | dex2oat 编译失败 | 有路径（root + 禁用 dex2oat + Frida），未验证 |
| 猫眼 | Yoda 人脸识别 | 物理硬约束（RGB 无深度） | **0%（不可修）** |
| 飞猪 | WebView 白屏 | 风控或资源加载 | 中（需要 debug logcat） |

**最关键的发现**：**猫眼的人脸识别不是配置问题，是物理定律**。RGB 模拟器相机没有 3D 深度信息，没有真实皮肤的次表面散射，没有 CMOS 噪声指纹。Yoda 的活体检测是从多个维度交叉验证的，模拟器能过的概率为 0。

---

## 5. framework 在真机上的可行性

**好消息**：framework 是真机立即可用的。

我们 framework 完全基于 adb，而 adb 对真机的支持比对模拟器好得多（USB 调试的 ABI 是真的 arm64-v8a、有真实的传感器、有真实的相机、Play Integrity 默认通过）。

```bash
# 用户操作
设置 → 关于手机 → 连点 7 次「版本号」→ 进入开发者模式
设置 → 开发者选项 → 打开 USB 调试
USB 连电脑 → 同意 RSA 指纹

adb devices
# 看到设备 → 直接跑 framework
```

代码**零修改**。我们的 adb 抽象层只关心"device_id"字符串，不管它是 emulator 还是真机。

**真实抢到票的概率**（在 framework + 真机 + 手动策略下）：

| 演出热度 | 概率 | 备注 |
|---|---|---|
| 普通演出 | 50-80% | 票源充足 |
| 中等热度 | 30-50% | 需要蹲回流 |
| 顶流（如王俊凯） | < 10% | 黄牛和粉丝团都头疼 |
| 顶流 + 蹲回流 | 10-30% | 5-25 分钟有人退票 |

---

## 6. 路径重新评估（可行性矩阵）

| 路径 | 投入 | 技术可行性 | 抢到票概率 | 推荐度 |
|---|---|---|---|---|
| **A. 继续模拟器（root + Magisk + 全面伪装）** | 2-4 周 | 中（不一定能过大麦 APM） | < 5% | ⭐ |
| **B. 真机 + framework** | 1 小时 | **高** | 10-30% | ⭐⭐⭐⭐⭐ |
| **C. mitmproxy API 重放** | 1-2 周开发 | 中（sign 每周变） | 30-50%（开发完成后） | ⭐⭐⭐ |
| **D. 千问 App 官方 AI 抢票** | 0 | 阿里官方，免费 | 不确定 | ⭐⭐⭐⭐ |
| **E. 加价代抢** | 200-800 元 | 黄牛职业水平 | 30-60% | ⭐⭐⭐ |
| **F. 蹲回流票 + 真人手点** | 0 | 普通用户最优路径 | 10-30% | ⭐⭐⭐⭐ |

---

## 7. 决策建议（基于上面所有事实）

**结论**：模拟器抢票这条路在我们当前的资源（1 台默认模拟器、有限时间、无专业反风控系统）下走不通。这不是 framework 不好，是**配置和环境的天花板**。

**务实路径**：

1. **保留项目**：framework 是有技术含量的（FastMCP + ADB + UI 自动化 + profile 系统 + 抓包），发布到 GitHub 作为 Android 自动化学习/教学项目。
2. **写诚实 README**：明确说明"模拟器抢票已被堵死，framework 适用于真机自动化"。
3. **不继续优化模拟器**：把精力释放给其它项目。
4. **抢王俊凯的票**：走 D（千问 App）+ F（蹲回流）路径，不依赖我们这个 framework。

**项目价值评估**：

| 维度 | 评分 |
|---|---|
| 技术学习价值 | ⭐⭐⭐⭐⭐ |
| framework 复用价值（真机自动化） | ⭐⭐⭐⭐ |
| 实际抢到王俊凯票的概率 | < 5% |
| 变现可能性 | ⭐ |
| 完成度 | ⭐⭐⭐⭐⭐（已发布 v0.2.3） |

---

## 8. 给未来的自己 / 接手这个项目的人

如果将来有人想继续这个项目，下面是必须知道的事：

1. **猫眼人脸识别永远过不去**。别浪费时间绕。
2. **大麦 APM 是 J2C + Qindroid**，dex2oat 在模拟器上必崩。唯一可能修的方式是 Frida hook + root + 全面伪装 build.prop。投入 vs 收益不划算。
3. **飞猪是 WebView 壳**，最有希望跑通，但需要先 debug logcat。
4. **framework 本身是好的**，真机上 100% 可用。建议改成"真机自动化教学项目"。
5. **抢到热门演唱会票 ≠ 自动化脚本**，是运气 + 资金 + 持续维护。

---

## 9. 附录：关键技术名词解释

- **J2C (Java-to-C)**：贾扬清团队的工具，把 Java 字节码编译成 C，再编译成 native lib，增加逆向难度。
- **Qindroid**：阿里基于 J2C 的 Android 加密方案，运行期用 native VM 执行混淆后的字节码。
- **houdini**：Intel 的 ARM → x86 翻译层，让 arm APK 能在 x86 模拟器上跑。但对自修改代码无效。
- **dex2oat**：Android Runtime (ART) 的 AOT 编译器，把 DEX 字节码编译成本地代码。在 ART 5.0+ 启用。
- **PRNU (Photo-Response Non-Uniformity)**：每个 CMOS 传感器特有的噪声指纹，用于传感器身份识别。模拟器"相机"没有这个指纹。
- **次表面散射 (Subsurface Scattering)**：光穿透物体表面后在内部散射的现象，真实皮肤有这种光学特性。
- **Yoda**：美团开源的人脸活体检测 SDK。
- **SafetyNet / Play Integrity**：Google 的设备完整性验证 API，App 用来检测 root / 模拟器。
- **Shamiko**：Zygisk 模块，用于在 LSPosed 框架下深度隐藏 root。

---

**文档版本**：v1.0
**日期**：2026-09-24
**状态**：决策前参考文档