# Zed Globalization

[![GitHub stars][stars-image]][stars-url]
[![Github Downloads][download-image]][download-url]
[![license][license-image]][license-url]

[Zed 编辑器](https://github.com/zed-industries/zed) 多语言本地化工具链，AI 驱动的全自动翻译与构建流水线。

## 下载安装

从 [Releases](https://github.com/x6nux/zed-globalization/releases/latest) 下载对应平台的预编译包：

| 平台 | 文件 | 安装方式 |
|------|------|---------|
| macOS (Apple Silicon) | `zed-globalization-zh-cn-macos-aarch64.dmg` | 打开 DMG 拖入 Applications（[见下方说明](#macos-安装说明)） |
| Windows (x64) | `zed-globalization-zh-cn-windows-x86_64.zip` | 解压后运行 `ZedG.exe` |
| Linux (x64) | `zed-globalization-zh-cn-linux-x86_64.tar.gz` | 解压到 `/usr/local` |
| Linux (x64 deb) | `zed-globalization-zh-cn-linux-x86_64.deb` | `sudo dpkg -i *.deb` |

**Windows Scoop 安装：**

```bash
scoop bucket add zed-globalization https://github.com/x6nux/zed-globalization -b scoop
scoop install zed-globalization
```

### macOS 安装说明

由于构建未经过 Apple 签名，macOS 会提示"应用已损坏，无法打开"。安装后在终端执行以下命令即可解决：

```bash
sudo xattr -rd com.apple.quarantine /Applications/ZedG.app
```

## 特性

- AI 自动扫描识别需翻译的 Rust 源文件
- 正则提取双引号字符串 + 代码上下文收集
- AI 并发翻译，三级降级策略（JSON -> XML CDATA -> 编号格式）
- 源码替换三层保护（过滤 + 语法修正 + 受保护区域跳过）
- JSON <-> Excel 双向转换，支持人工校对
- 跨平台构建（Windows / Linux / macOS），含应用图标
- GitHub Actions 全自动流水线：扫描 -> 翻译 -> 构建 -> 发布

## 自动化流水线

```
01-scan (每日定时)     扫描 Zed 新版本，提取待翻译字符串
       |
02-translate           AI 并发翻译，推送到 i18n 分支
       |
03-build               三平台编译 + patch_agent_env 补丁，生成 Release
       |
04-update-scoop        更新 Scoop Manifest
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
│   ├── 01-scan.yml         # 定时扫描 + 字符串提取
│   ├── 02-translate.yml    # AI 翻译
│   ├── 03-build.yml        # 多平台编译 + 发布
│   └── 04-update-scoop.yml # Scoop Manifest 更新
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
