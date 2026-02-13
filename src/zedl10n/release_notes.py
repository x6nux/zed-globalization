"""获取并翻译 Zed Release Notes"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from .utils import AIConfig

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """你是一个专业的技术文档翻译员。请将以下 Zed 编辑器的英文 Release Notes 翻译为{lang}。

翻译规则:
1. 保留所有 Markdown 格式（标题、列表、链接、代码块、图片等）
2. 保留所有 GitHub 用户名（@xxx）、PR 编号（#xxx）、链接 URL 不翻译
3. 技术术语如无通用译法则保留英文（如 LSP、GPU、WebSocket 等）
4. 保持简洁专业的技术文档风格
5. 直接输出翻译结果，不要添加说明或注释"""

_LANG_NAMES: dict[str, str] = {
    "zh-CN": "简体中文",
    "zh-TW": "繁體中文",
    "ja": "日本語",
    "ko": "한국어",
}


def _count_translation_keys(translation_file: str) -> int:
    """统计翻译 JSON 文件中的翻译键总数"""
    p = Path(translation_file)
    if not p.exists():
        return 0
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return sum(len(v) for v in data.values() if isinstance(v, dict))
    except Exception as e:
        log.warning("读取翻译文件失败: %s", e)
        return 0


def _build_project_header(
    version: str, lang: str, key_count: int,
) -> str:
    """生成项目说明头部"""
    lang_name = _LANG_NAMES.get(lang, lang)
    lang_lower = lang.lower()

    lines = [
        f"## ZedG {version}",
        "",
        f"> [Zed](https://zed.dev) 编辑器的{lang_name}本地化构建版本，"
        "由 [zed-globalization](https://github.com/x6nux/zed-globalization) "
        "自动翻译并编译。",
        "",
        f"**目标语言**: {lang_name} (`{lang}`)",
        "",
        f"**翻译键数**: {key_count:,}" if key_count else "",
        "",
        "**本补丁做了什么**：通过 AI 自动提取 Zed 源码中的用户可见字符串，"
        f"翻译为{lang_name}后直接替换源码并重新编译，"
        "无需运行时 i18n 框架，零性能开销。",
        "",
        "### 安装方式",
        "",
        "**macOS (Apple Silicon)**",
        "",
        "Homebrew（推荐）：",
        "```bash",
        "brew tap x6nux/zedg && brew install --cask zedg",
        "```",
        "",
        "DMG 手动安装：从上方下载 DMG，打开后将 ZedG 拖入 Applications。"
        "首次打开如提示「应用已损坏」，执行：",
        "```bash",
        "sudo xattr -rd com.apple.quarantine /Applications/ZedG.app",
        "```",
        "",
        "**Linux (x86_64)**",
        "```bash",
        f"# deb 包安装",
        f"sudo dpkg -i zedg-{lang_lower}-linux-x86_64-{version}.deb",
        "",
        f"# 或解压 tar.gz",
        f"sudo tar -xzf zedg-{lang_lower}-linux-x86_64-{version}.tar.gz -C /",
        "```",
        "",
        "**Windows (x86_64)**",
        "",
        "Scoop（推荐）：",
        "```bash",
        "scoop bucket add zed-globalization https://github.com/x6nux/zed-globalization -b scoop",
        "scoop install zed-globalization",
        "```",
        "",
        "或解压 zip 后直接运行 `ZedG.exe`。",
        "",
        "---",
        "",
    ]
    return "\n".join(line for line in lines if line is not None)


def fetch_release_notes(version: str) -> str:
    """从 GitHub API 获取 Zed 指定版本的 Release Notes"""
    import urllib.request

    urls = [
        f"https://api.github.com/repos/zed-industries/zed/releases/tags/{version}",
        "https://api.github.com/repos/zed-industries/zed/releases/latest",
    ]
    for url in urls:
        try:
            req = urllib.request.Request(
                url, headers={"Accept": "application/vnd.github+json"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
                body = data.get("body", "")
                if body:
                    log.info("获取到 Release Notes (来源: %s)", url)
                    return body
        except Exception as e:
            log.debug("请求失败 %s: %s", url, e)
    return ""


def translate_notes(
    notes: str, lang: str, ai_cfg: AIConfig,
) -> str:
    """调用 AI 翻译 Release Notes"""
    from openai import OpenAI

    client = OpenAI(base_url=ai_cfg.base_url, api_key=ai_cfg.api_key)
    system = _SYSTEM_PROMPT.format(lang=lang)

    try:
        resp = client.chat.completions.create(
            model=ai_cfg.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": notes},
            ],
            temperature=0,
        )
        result = (resp.choices[0].message.content or "").strip()
        if result:
            log.info("Release Notes 翻译完成 (%d 字符)", len(result))
            return result
    except Exception as e:
        log.warning("翻译 Release Notes 失败: %s", e)
    return ""


def generate_release_body(
    version: str,
    lang: str,
    ai_cfg: AIConfig,
    output: str,
    translation_file: str = "",
) -> None:
    """获取、翻译并保存 Release Notes（含项目说明头部）"""
    key_count = (
        _count_translation_keys(translation_file) if translation_file else 0
    )
    header = _build_project_header(version, lang, key_count)

    notes = fetch_release_notes(version)
    parts: list[str] = [header]

    if notes:
        parts.append("## Zed 官方更新日志\n")
        translated = translate_notes(notes, lang, ai_cfg)
        if translated:
            parts.append(translated)
        else:
            log.warning("翻译失败，使用英文原文")
            parts.append(notes)
    else:
        log.warning("未获取到 Release Notes")
        parts.append(
            f"查看官方更新日志: "
            f"https://github.com/zed-industries/zed/releases/tag/{version}"
        )

    Path(output).write_text("\n".join(parts), encoding="utf-8")
    log.info("Release body 已保存: %s", output)


def run(args: argparse.Namespace) -> None:
    """CLI 入口"""
    ai_cfg = AIConfig(
        base_url=args.base_url, api_key=args.api_key,
        model=args.model, concurrency=args.concurrency,
    )
    ai_cfg.validate()
    translation_file = getattr(args, "translation_file", "") or ""
    generate_release_body(
        args.version, args.lang, ai_cfg, args.output, translation_file,
    )
