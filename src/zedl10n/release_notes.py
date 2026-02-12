"""获取并翻译 Zed Release Notes"""

from __future__ import annotations

import argparse
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


def fetch_release_notes(version: str) -> str:
    """从 GitHub API 获取 Zed 指定版本的 Release Notes"""
    import urllib.request
    import json

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
    version: str, lang: str, ai_cfg: AIConfig, output: str,
) -> None:
    """获取、翻译并保存 Release Notes"""
    notes = fetch_release_notes(version)

    parts: list[str] = [f"## ZedG {version} 更新内容\n"]

    if notes:
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
    generate_release_body(args.version, args.lang, ai_cfg, args.output)
