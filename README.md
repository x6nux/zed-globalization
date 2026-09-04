# Zed Globalization — Zed 编辑器汉化版 / 中文版 / 多语言版

[![GitHub stars][stars-image]][stars-url]
[![Github Downloads][download-image]][download-url]
[![license][license-image]][license-url]

[Zed 编辑器](https://github.com/zed-industries/zed) 汉化版（中文版），支持简体中文、繁体中文、日语、韩语等多语言。AI 驱动的全自动翻译与构建流水线，开箱即用。

> **Zed 汉化版** | Zed 中文版 | Zed Chinese | Zed Localized | Zed 多语言 | Zed 国际化 | Zed i18n | Zed l10n

## 下载安装

从 [Releases](https://github.com/x6nux/zed-globalization/releases/latest) 下载对应平台的预编译包：

| 平台 | 文件 | 安装方式 |
|------|------|---------|
| macOS (Universal) | `zedg-zh-cn-macos-universal-*.dmg` | `brew tap x6nux/zedg && brew install --cask zedg`（自动按架构选包，[更多方式](#macos-安装)） |
| macOS (Apple Silicon) | `zedg-zh-cn-macos-aarch64-*.dmg` | DMG 手动安装 |
| macOS (Intel) | `zedg-zh-cn-macos-x86_64-*.dmg` | DMG 手动安装 |
| Windows (x64) | `zedg-zh-cn-windows-x86_64-*.zip` | `scoop install zedg`（[更多方式](#windows-scoop-安装)） |
| Windows (ARM64) | `zedg-zh-cn-windows-aarch64-*.zip` | 解压后运行 `ZedG.exe` |
| Linux (x64) | `zedg-zh-cn-linux-x86_64-*.tar.gz` | 解压到 `/usr/local` |
| Linux (x64 deb) | `zedg-zh-cn-linux-x86_64-*.deb` | `sudo dpkg -i *.deb` |
| Linux (x64 rpm) | `zedg-zh-cn-linux-x86_64-*.rpm` | `sudo dnf install *.rpm` |
| Linux (ARM64) | `zedg-zh-cn-linux-aarch64-*.tar.gz` | 解压到 `/usr/local` |
| Linux (ARM64 deb) | `zedg-zh-cn-linux-aarch64-*.deb` | `sudo dpkg -i *.deb` |
| Linux (ARM64 rpm) | `zedg-zh-cn-linux-aarch64-*.rpm` | `sudo dnf install *.rpm` |

### macOS 安装

**稳定版（推荐）：**

```bash
# 首次安装
brew tap x6nux/zedg
brew install --cask zedg

# 手动更新
brew update && brew upgrade --cask zedg
```

**预览版（Pre-release）：**

```bash
brew tap x6nux/zedg
brew install --cask zedg-preview
```

> **自动更新（可选）：** 启用后 Homebrew 会每 12 小时自动检查并升级**所有**已安装的 formulae 和 cask（不支持仅指定单个包）。
> ```bash
> # 启用
> brew tap homebrew/autoupdate
> brew autoupdate start 43200 --upgrade
>
> # 关闭
> brew autoupdate stop
>
> # 查看状态
> brew autoupdate status
> ```

**DMG 手动安装：**

从 Releases 下载 DMG（Universal Binary，同时支持 Apple Silicon 和 Intel），打开后将 ZedG 拖入 Applications。由于构建未经 Apple 签名，首次打开会提示"应用已损坏"，在终端执行以下命令即可：

```bash
sudo xattr -rd com.apple.quarantine /Applications/ZedG.app
```

### Windows Scoop 安装

**稳定版：**

```powershell
# 首次安装
scoop bucket add zedg https://github.com/x6nux/scoop-zedg
scoop install zedg

# 手动更新
scoop update zedg
```

**预览版（Pre-release）：**

```powershell
scoop bucket add zedg https://github.com/x6nux/scoop-zedg
scoop install zedg-preview
```

**生态兼容版（覆盖官方 zed 命令）：**

```powershell
scoop bucket add zedg https://github.com/x6nux/scoop-zedg
scoop install zedg-compat
```

> **`zedg` 与 `zedg-compat` 的区别：** 两者安装同一 ZedG 编辑器，区别在命令行 shim：
> - `zedg` — 只注册 `zedg` 命令，不影响官方 Zed（推荐已单独安装官方 Zed 的用户）
> - `zedg-compat` — 额外注册 `zed` 命令，生态工具（git difftool、终端 `zed .` 等）会自动识别 ZedG 为默认编辑器。
>   若之前安装过官方 Zed，建议先卸载或重命名其 `zed.exe`，避免命令冲突。
>
> 两者可随时切换：`scoop uninstall zedg && scoop install zedg-compat`（反之亦然）。

> **自动更新（可选）：** 通过 Windows 计划任务每天定时更新（需要管理员权限）。
> ```powershell
> # 启用（每天中午 12:00 自动更新 ZedG）
> schtasks /create /tn "ZedGUpdate" /tr "powershell -Command 'scoop update zedg'" /sc daily /st 12:00
>
> # 关闭
> schtasks /delete /tn "ZedGUpdate" /f
> ```

## 卸载

### macOS（Homebrew）

```bash
# 卸载 ZedG（稳定版 / 预览版同理）
brew uninstall --cask zedg
brew untap x6nux/zedg   # 可选：移除 tap 源
```

若启用了自动更新，先取消定时任务再卸载：

```bash
brew autoupdate stop        # 停止 12 小时定时更新
brew untap homebrew/autoupdate   # 可选：彻底移除 autoupdate
```

### Windows（Scoop）

```powershell
# 卸载 ZedG（稳定版 / 预览版 / 兼容版同理）
scoop uninstall zedg

# 若启用了自动更新，先删除计划任务
schtasks /delete /tn "ZedGUpdate" /f
```

### Windows（NSIS 安装包）

双击运行安装目录下的 `Uninstall.exe`（或在 "设置 → 应用" 中卸载 ZedG）。卸载程序会：
- 删除 ZedG 程序文件与 PATH 注册
- 若曾勾选 "覆盖官方 Zed 安装"，自动还原官方 `zed.exe`

### Linux

```bash
# deb 包（Ubuntu / Debian）
sudo apt remove zedg

# rpm 包（Fedora / RHEL）
sudo dnf remove zedg

# tar.gz 手动安装（解压到 /usr/local 的反向操作）
sudo rm -f /usr/local/bin/zedg /usr/local/bin/zed
sudo rm -f /usr/local/libexec/zedg /usr/local/libexec/zed-cli
sudo rm -rf /usr/local/lib/zedg
sudo rm -f /usr/local/share/applications/zedg.desktop
sudo rm -f /usr/local/share/icons/hicolor/{512x512,1024x1024}/apps/zedg.png
sudo rm -f /usr/local/bin/zedg-activate
sudo ldconfig
```

## 特性

- AI 自动扫描识别需翻译的 Rust 源文件
- 正则提取双引号字符串 + 代码上下文收集
- AI 并发翻译，三级降级策略（JSON -> XML CDATA -> 编号格式）
- 源码替换三层保护（过滤 + 语法修正 + 受保护区域跳过）
- JSON <-> Excel 双向转换，支持人工校对
- 跨平台构建（Windows / Linux / macOS），含应用图标
- GitHub Actions 全自动流水线：扫描 -> 翻译 -> 构建 -> 发布
- **可选覆盖官方 Zed**：Windows 安装向导（NSIS 组件页勾选）/ Scoop（`zedg-compat` 包）/ macOS & Linux（`zedg-activate.sh` 一键激活，`--revert` 还原）

## 自动化流水线

```
01-translate (定时/手动)   扫描 Zed 新版本，提取并翻译字符串
       |
02-build                   三平台编译 + patch_agent_env 补丁，生成 Release
       |
       ├── 03-update-scoop      更新 Scoop Manifest
       └── 04-update-homebrew   更新 Homebrew Cask
```

## 本地使用

### 安装工具

```bash
# 基础安装（仅替换功能）
pip install .

# 含 AI 翻译功能
pip install ".[ai]"

# 全部功能
pip install ".[all]"
```

### 分步执行

```bash
# 1. AI 扫描：识别哪些 .rs 文件需要翻译
zedl10n scan --source-root zed

# 2. 提取字符串
zedl10n extract --source-root zed --output string.json

# 3. AI 翻译
zedl10n translate --input string.json --output i18n/zh-CN.json --mode full

# 4. 替换源码
zedl10n replace --input i18n/zh-CN.json --source-root zed
```

### 一键流水线

```bash
zedl10n pipeline --source-root zed --lang zh-CN --mode full
```

### 本地构建

```bash
git clone https://github.com/zed-industries/zed.git
zedl10n replace --input i18n/zh-CN.json --source-root zed
python3 patch_agent_env.py --source-root zed
cd zed && cargo build --release
```

### 生态兼容：让系统把 ZedG 当作 `zed`（可选）

生态工具（git difftool、终端 `zed .`、"默认编辑器"选择器）通常找名为 `zed` 的命令。
ZedG 提供三种方式注册，均**不破坏官方 Zed 安装**（可随时还原）：

**Windows（NSIS 安装包）**

安装向导的组件页勾选 **"覆盖官方 Zed 安装"**：
- 自动备份官方 `zed.exe` → `zed.exe.official.bak` 后替换
- 卸载 ZedG 时自动还原官方版本

**Windows（Scoop）**

安装 `zedg-compat` 包（额外 shim `zed` 命令）：

```powershell
scoop install zedg-compat
```

**macOS / Linux（tar.gz / deb / rpm 手动安装）**

```bash
zedg-activate.sh            # 激活：创建 ~/.local/bin/zed 链接 + 注册 desktop 入口
zedg-activate.sh --status   # 查看当前接管状态
zedg-activate.sh --revert   # 一键还原官方状态（官方 zed 已自动备份为 zed.orig）
```

> Linux deb/rpm 包还会自动注册 `zedg.desktop` 并关联 `text/plain`，应用列表直接可见。

> **`patch_agent_env.py` 补丁说明：** Zed 源码中 `agent_server_store.rs` 会强制将 `ANTHROPIC_API_KEY` 设为空字符串，导致用户系统中已配置的 API Key 被清除；同时 `claude.rs` 的 `connect()` 方法没有像 Codex/Gemini 那样从系统环境变量读取并透传 API Key。该补丁自动修复这两个问题：
> - **补丁 1**：删除 `agent_server_store.rs` 中 `env.insert("ANTHROPIC_API_KEY", "")` 的强制清空行
> - **补丁 2**：在 `claude.rs` 的 `connect()` 中注入环境变量透传逻辑，将 `ANTHROPIC_API_KEY`、`ANTHROPIC_BASE_URL`、Bedrock/Vertex 相关变量及 `AWS_*`、`GOOGLE_CLOUD_*` 前缀变量传递给 Claude Code 进程
>
> 脚本幂等安全：通过 `[ZED_GLOBALIZATION_PATCH]` 标记检测是否已打补丁，重复运行自动跳过。支持 `--dry-run` 仅预览不修改。

## AI 配置

| 环境变量 | CLI 参数 | 说明 | 默认值 |
|----------|----------|------|--------|
| `AI_BASE_URL` | `--base-url` | API 地址 | `https://api.openai.com/v1` |
| `AI_API_KEY` | `--api-key` | API 密钥 | 无（必填） |
| `AI_MODEL` | `--model` | 模型名称 | `gpt-4o-mini` |
| `AI_CONCURRENCY` | `--concurrency` | 并发数 | `5` |

支持任何 OpenAI 兼容 API。优先级：CLI 参数 > 环境变量 > 默认值。

## 项目结构

```
zed-globalization/
├── .github/workflows/
│   ├── 01-translate.yml        # 定时扫描 + AI 翻译
│   ├── 02-build.yml            # 多平台编译 + 发布
│   ├── 03-update-scoop.yml    # Scoop Manifest 更新
│   └── 04-update-homebrew.yml # Homebrew Cask 更新
├── config/
│   └── glossary.yaml       # 翻译术语表
├── i18n/                   # 翻译文件（zh-CN, ja, ko 等）
├── src/zedl10n/
│   ├── cli.py              # CLI 入口（scan/extract/translate/replace/convert/pipeline）
│   ├── scan.py             # AI 扫描识别待翻译文件
│   ├── extract.py          # 正则提取字符串 + 上下文
│   ├── translate.py        # AI 并发翻译（三级降级）
│   ├── replace.py          # 源码替换（多级路径解析 + 三层保护）
│   ├── convert.py          # JSON <-> Excel 转换
│   └── utils.py            # 共享工具与配置
├── patch_agent_env.py      # 编译前补丁：修复 Agent 环境变量透传
└── pyproject.toml
```

## 替换保护机制

源码替换时通过多层机制保障 Rust 编译安全：

1. **翻译过滤**：跳过纯 ASCII 标点字符串，避免破坏数组语法
2. **受保护区域**：跳过字节字符串（`b""`/`br#""#`）和属性宏（`#[action(...)]`）内的替换
3. **引号转义**：译文中的双引号自动转义为 `\"`
4. **语法修正**：替换后自动将字符串间的中文标点（`、`/`，`/`；`）还原为 ASCII 标点

## 鸣谢

- [Zed](https://github.com/zed-industries/zed)
- [deevus/zed-windows-builds](https://github.com/deevus/zed-windows-builds)
- [Nriver/zed-translation](https://github.com/Nriver/zed-translation)

## 许可证

[MIT](LICENSE)

[stars-url]: https://github.com/x6nux/zed-globalization/stargazers
[stars-image]: https://img.shields.io/github/stars/x6nux/zed-globalization?style=flat-square&logo=github
[download-url]: https://github.com/x6nux/zed-globalization/releases/latest
[download-image]: https://img.shields.io/github/downloads/x6nux/zed-globalization/total?style=flat-square&logo=github
[license-url]: https://github.com/x6nux/zed-globalization/blob/main/LICENSE
[license-image]: https://img.shields.io/github/license/x6nux/zed-globalization?style=flat-square

---

<details>
<summary>关键词 / Keywords</summary>

Zed 汉化版, Zed 中文版, Zed 编辑器汉化, Zed 编辑器中文版, Zed 编辑器中文, Zed 中文汉化,
Zed 多语言版本, Zed 国际化, Zed 本地化, Zed 翻译, Zed 简体中文, Zed 繁体中文,
Zed Chinese, Zed Japanese, Zed Korean, Zed Localization, Zed Globalization,
Zed i18n, Zed l10n, Zed Translation, Zed Editor Chinese, Zed Editor Localized,
Zed 代替 VSCode, Zed 代替 Cursor, Rust 编辑器中文版, 高性能编辑器汉化

</details>
