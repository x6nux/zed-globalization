# Zed Globalization

[![GitHub stars][stars-image]][stars-url]
[![Github Downloads][download-image]][download-url]
[![license][license-image]][license-url]

[简体中文](../README.md)|**English**|[日本語](README.ja.md)|[한국어](README.ko.md)

An AI-driven localization toolchain for the [Zed Editor](https://github.com/zed-industries/zed), with a fully automated translation and build pipeline.

## Download

Get the pre-built binaries from [Releases](https://github.com/x6nux/zed-globalization/releases/latest):

| Platform | File | Installation |
|----------|------|-------------|
| macOS (Apple Silicon) | `zed-globalization-zh-cn-macos-aarch64.dmg` | `brew tap x6nux/zedg && brew install --cask zedg` ([more](#macos-installation)) |
| Windows (x64) | `zed-globalization-zh-cn-windows-x86_64.zip` | Extract and run `zed.exe` |
| Linux (x64) | `zed-globalization-zh-cn-linux-x86_64.tar.gz` | Extract to `/usr/local` |
| Linux (x64 deb) | `zed-globalization-zh-cn-linux-x86_64.deb` | `sudo dpkg -i *.deb` |

### macOS Installation

**Homebrew (Recommended):**

```bash
brew tap x6nux/zedg
brew install --cask zedg
```

**DMG Manual Install:**

Download the DMG from Releases, open it and drag ZedG to Applications. Since the build is not Apple-signed, macOS will show a "damaged" warning on first launch. Run the following command to fix it:

```bash
sudo xattr -rd com.apple.quarantine /Applications/ZedG.app
```

**Windows Scoop:**

```bash
scoop bucket add zed-globalization https://github.com/x6nux/zed-globalization -b scoop
scoop install zed-globalization
```

## Features

- AI-powered scanning to identify translatable Rust source files
- Regex-based string extraction with code context collection
- Concurrent AI translation with 3-level fallback (JSON -> XML CDATA -> numbered format)
- Source replacement with 3-layer protection (filtering + syntax repair + protected region skipping)
- Bidirectional JSON <-> Excel conversion for manual review
- Cross-platform builds (Windows / Linux / macOS) with app icons
- Fully automated GitHub Actions pipeline: scan -> translate -> build -> release

## Automation Pipeline

```
01-translate (cron/manual)   Detect new Zed releases, extract and translate strings
       |
02-build                     Cross-platform compilation + patch_agent_env, create Release
       |
       ├── 03-update-scoop        Update Scoop Manifest
       └── 04-update-homebrew     Update Homebrew Cask
```

## Local Usage

### Install

```bash
# Basic (replacement only)
pip install .

# With AI translation
pip install ".[ai]"

# All features
pip install ".[all]"
```

### Step by Step

```bash
# 1. AI scan: identify .rs files needing translation
zedl10n scan --source-root zed

# 2. Extract strings
zedl10n extract --source-root zed --output string.json

# 3. AI translate
zedl10n translate --input string.json --output i18n/zh-CN.json --mode full

# 4. Replace source
zedl10n replace --input i18n/zh-CN.json --source-root zed
```

### One-click Pipeline

```bash
zedl10n pipeline --source-root zed --lang zh-CN --mode full
```

### Local Build

```bash
git clone https://github.com/zed-industries/zed.git
zedl10n replace --input i18n/zh-CN.json --source-root zed
cd zed && cargo build --release
```

## AI Configuration

| Env Variable | CLI Flag | Description | Default |
|-------------|----------|-------------|---------|
| `AI_BASE_URL` | `--base-url` | API endpoint | `https://api.openai.com/v1` |
| `AI_API_KEY` | `--api-key` | API key | Required |
| `AI_MODEL` | `--model` | Model name | `gpt-4o-mini` |
| `AI_CONCURRENCY` | `--concurrency` | Concurrency | `5` |

Compatible with any OpenAI-compatible API. Priority: CLI flag > env variable > default.

## Project Structure

```
zed-globalization/
├── .github/workflows/
│   ├── 01-translate.yml        # Scheduled scan + AI translation
│   ├── 02-build.yml            # Cross-platform build + release
│   ├── 03-update-scoop.yml    # Scoop Manifest update
│   └── 04-update-homebrew.yml # Homebrew Cask update
├── config/
│   └── glossary.yaml       # Translation glossary
├── i18n/                   # Translation files (zh-CN, ja, ko, etc.)
├── src/zedl10n/
│   ├── cli.py              # CLI entry (scan/extract/translate/replace/convert/pipeline)
│   ├── scan.py             # AI scan for translatable files
│   ├── extract.py          # Regex string extraction + context
│   ├── translate.py        # Concurrent AI translation (3-level fallback)
│   ├── replace.py          # Source replacement (3-layer protection)
│   ├── convert.py          # JSON <-> Excel conversion
│   └── utils.py            # Shared utilities and config
└── pyproject.toml
```

## Replacement Protection

Multiple layers ensure Rust compilation safety during source replacement:

1. **Translation filtering**: Skip pure ASCII punctuation strings to preserve array syntax
2. **Protected regions**: Skip byte strings (`b""`/`br#""#`) and attribute macros (`#[action(...)]`)
3. **Quote escaping**: Auto-escape double quotes in translations to `\"`
4. **Syntax repair**: Auto-restore Chinese punctuation between strings to ASCII equivalents

## Acknowledgements

- [Zed](https://github.com/zed-industries/zed)
- [deevus/zed-windows-builds](https://github.com/deevus/zed-windows-builds)
- [Nriver/zed-translation](https://github.com/Nriver/zed-translation)

## License

[MIT](../LICENSE)

[stars-url]: https://github.com/x6nux/zed-globalization/stargazers
[stars-image]: https://img.shields.io/github/stars/x6nux/zed-globalization?style=flat-square&logo=github
[download-url]: https://github.com/x6nux/zed-globalization/releases/latest
[download-image]: https://img.shields.io/github/downloads/x6nux/zed-globalization/total?style=flat-square&logo=github
[license-url]: https://github.com/x6nux/zed-globalization/blob/main/LICENSE
[license-image]: https://img.shields.io/github/license/x6nux/zed-globalization?style=flat-square
