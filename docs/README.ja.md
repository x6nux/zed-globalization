# Zed Globalization

[![GitHub stars][stars-image]][stars-url]
[![Github Downloads][download-image]][download-url]
[![license][license-image]][license-url]

[简体中文](../README.md)|[English](README.en.md)|**日本語**|[한국어](README.ko.md)

[Zed エディタ](https://github.com/zed-industries/zed) の多言語ローカライズツールチェーン。AI 駆動の全自動翻訳・ビルドパイプライン。

## ダウンロード

[Releases](https://github.com/x6nux/zed-globalization/releases/latest) からビルド済みバイナリをダウンロード：

| プラットフォーム | ファイル | インストール方法 |
|-----------------|---------|----------------|
| macOS (Apple Silicon) | `zed-globalization-zh-cn-macos-aarch64.dmg` | `brew tap x6nux/zedg && brew install --cask zedg`（[詳細](#macos-インストール)） |
| Windows (x64) | `zed-globalization-zh-cn-windows-x86_64.zip` | 解凍して `zed.exe` を実行 |
| Linux (x64) | `zed-globalization-zh-cn-linux-x86_64.tar.gz` | `/usr/local` に解凍 |
| Linux (x64 deb) | `zed-globalization-zh-cn-linux-x86_64.deb` | `sudo dpkg -i *.deb` |

### macOS インストール

**Homebrew（推奨）：**

```bash
brew tap x6nux/zedg
brew install --cask zedg
```

**DMG 手動インストール：**

Releases から DMG をダウンロードし、ZedG を Applications にドラッグします。Apple 署名されていないため、初回起動時に「アプリが壊れています」と表示されます。以下のコマンドで解決できます：

```bash
sudo xattr -rd com.apple.quarantine /Applications/ZedG.app
```

**Windows Scoop：**

```bash
scoop bucket add zed-globalization https://github.com/x6nux/zed-globalization -b scoop
scoop install zed-globalization
```

## 特徴

- AI による翻訳対象 Rust ソースファイルの自動スキャン
- 正規表現による文字列抽出 + コードコンテキスト収集
- AI 並列翻訳、3段階フォールバック（JSON -> XML CDATA -> 番号形式）
- ソース置換の3層保護（フィルタ + 構文修正 + 保護領域スキップ）
- JSON <-> Excel 双方向変換、手動レビュー対応
- クロスプラットフォームビルド（Windows / Linux / macOS）、アプリアイコン付き
- GitHub Actions 全自動パイプライン：スキャン -> 翻訳 -> ビルド -> リリース

## 自動化パイプライン

```
01-translate (定時/手動)   Zed の新バージョンを検出、文字列を抽出・翻訳
       |
02-build                   3プラットフォームコンパイル + patch_agent_env、Release を作成
       |
       ├── 03-update-scoop      Scoop Manifest を更新
       └── 04-update-homebrew   Homebrew Cask を更新
```

## ローカル使用

### インストール

```bash
# 基本（置換機能のみ）
pip install .

# AI 翻訳機能付き
pip install ".[ai]"

# 全機能
pip install ".[all]"
```

### ステップ実行

```bash
# 1. AI スキャン：翻訳が必要な .rs ファイルを識別
zedl10n scan --source-root zed

# 2. 文字列抽出
zedl10n extract --source-root zed --output string.json

# 3. AI 翻訳
zedl10n translate --input string.json --output i18n/zh-CN.json --mode full

# 4. ソース置換
zedl10n replace --input i18n/zh-CN.json --source-root zed
```

### ワンクリックパイプライン

```bash
zedl10n pipeline --source-root zed --lang zh-CN --mode full
```

### ローカルビルド

```bash
git clone https://github.com/zed-industries/zed.git
zedl10n replace --input i18n/zh-CN.json --source-root zed
cd zed && cargo build --release
```

## AI 設定

| 環境変数 | CLI オプション | 説明 | デフォルト |
|---------|---------------|------|----------|
| `AI_BASE_URL` | `--base-url` | API エンドポイント | `https://api.openai.com/v1` |
| `AI_API_KEY` | `--api-key` | API キー | 必須 |
| `AI_MODEL` | `--model` | モデル名 | `gpt-4o-mini` |
| `AI_CONCURRENCY` | `--concurrency` | 並列数 | `5` |

OpenAI 互換の任意の API に対応。優先度：CLI オプション > 環境変数 > デフォルト値。

## プロジェクト構成

```
zed-globalization/
├── .github/workflows/
│   ├── 01-translate.yml        # 定時スキャン + AI 翻訳
│   ├── 02-build.yml            # マルチプラットフォームビルド + リリース
│   ├── 03-update-scoop.yml    # Scoop Manifest 更新
│   └── 04-update-homebrew.yml # Homebrew Cask 更新
├── config/
│   └── glossary.yaml       # 翻訳用語集
├── i18n/                   # 翻訳ファイル（zh-CN, ja, ko など）
├── src/zedl10n/
│   ├── cli.py              # CLI エントリ（scan/extract/translate/replace/convert/pipeline）
│   ├── scan.py             # AI スキャン
│   ├── extract.py          # 正規表現抽出 + コンテキスト
│   ├── translate.py        # AI 並列翻訳（3段階フォールバック）
│   ├── replace.py          # ソース置換（3層保護）
│   ├── convert.py          # JSON <-> Excel 変換
│   └── utils.py            # 共有ユーティリティと設定
└── pyproject.toml
```

## 置換保護メカニズム

ソース置換時に Rust コンパイルの安全性を保障する多層メカニズム：

1. **翻訳フィルタ**：純粋な ASCII 記号文字列をスキップし、配列構文の破壊を防止
2. **保護領域**：バイト文字列（`b""`/`br#""#`）と属性マクロ（`#[action(...)]`）内の置換をスキップ
3. **引用符エスケープ**：翻訳文中のダブルクォートを自動的に `\"` にエスケープ
4. **構文修正**：文字列間の中国語句読点を ASCII 句読点に自動復元

## 謝辞

- [Zed](https://github.com/zed-industries/zed)
- [deevus/zed-windows-builds](https://github.com/deevus/zed-windows-builds)
- [Nriver/zed-translation](https://github.com/Nriver/zed-translation)

## ライセンス

[MIT](../LICENSE)

[stars-url]: https://github.com/x6nux/zed-globalization/stargazers
[stars-image]: https://img.shields.io/github/stars/x6nux/zed-globalization?style=flat-square&logo=github
[download-url]: https://github.com/x6nux/zed-globalization/releases/latest
[download-image]: https://img.shields.io/github/downloads/x6nux/zed-globalization/total?style=flat-square&logo=github
[license-url]: https://github.com/x6nux/zed-globalization/blob/main/LICENSE
[license-image]: https://img.shields.io/github/license/x6nux/zed-globalization?style=flat-square
