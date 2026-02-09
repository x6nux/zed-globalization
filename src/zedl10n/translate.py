"""AI 并发翻译，内置智能过滤"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import random
from pathlib import Path

from .utils import (
    AIConfig, ProgressBar, TranslationDict,
    build_glossary_section, extract_crate_name,
    load_json, parse_json_response, parse_numbered_response,
    parse_xml_response, save_json,
)

log = logging.getLogger(__name__)

_SYSTEM_PROMPT_TEMPLATE = """你是一个专业的软件界面翻译专家，正在翻译 Zed 代码编辑器的用户界面。

目标语言: {lang}

翻译规则:
1. 对需要翻译的 UI 字符串，返回准确、自然的翻译
2. 对不需要翻译的内容，返回空字符串 ""。不需要翻译的内容包括：
   - URL、文件路径、目录路径
   - 纯数字、版本号
   - 纯标点符号、特殊字符
   - 编程标识符（变量名、函数名、类名）
   - API 名称、HTTP 方法、MIME 类型
   - 正则表达式
   - 代码片段、命令行指令
   - 只有一两个字母的缩写
3. 保持快捷键占位符不变（如 {{key}}）
4. 保持字符串中的格式占位符不变（如 {{}}、%s、{{0}}）
5. 严禁将 ASCII 标点替换为中文标点。逗号保持 ","，不要变为 "、" 或 "，"；分号保持 ";"，不要变为 "；"

{glossary_section}

输入格式: JSON 对象 {{"原文": ""}}
输出格式: JSON 对象 {{"原文": "译文"}}（不需翻译的返回空字符串）

重要: 只返回 JSON 对象，不要添加任何解释文字或 markdown 标记。"""

_USER_PROMPT_TEMPLATE = """文件: {file_path}
模块: {crate_name}

以下是需要翻译的字符串及其代码上下文:

{entries}

请翻译以上字符串，返回 JSON 对象。"""

_XML_FALLBACK_INSTRUCTION = """
（重要：此次请使用 XML 格式返回，不要使用 JSON）

输出格式:
<translations>
<t><s><![CDATA[原文1]]></s><v>译文1</v></t>
<t><s><![CDATA[原文2]]></s><v></v></t>
</translations>

注意：原文必须用 <![CDATA[...]]> 包裹，防止特殊字符干扰 XML 解析。
不需要翻译的字符串，<v> 标签内留空。只返回 XML，不要添加解释。"""


def _build_numbered_instruction(count: int) -> str:
    """构建编号格式降级指令"""
    return f"""
（重要：此次请使用编号格式返回，不要使用 JSON 或 XML）

按上面的字符串编号，逐条返回翻译结果。格式如下:
[##1##]译文1
[##2##]
[##3##]译文3

规则:
- 每条以 [##编号##] 开头，紧跟译文（同一行）
- 不需要翻译的字符串，[##编号##] 后面留空即可
- 不要添加任何解释文字
- 必须包含所有编号，从 1 到 {count}"""


def _build_entries_text(
    strings: dict[str, str], contexts: dict[str, dict] | None,
) -> str:
    """构建待翻译条目文本（含上下文）"""
    lines: list[str] = []
    for i, (s, _) in enumerate(strings.items(), 1):
        lines.append(f'{i}. "{s}"')
        if contexts and s in contexts:
            ctx = contexts[s].get("context", "")
            if ctx:
                lines.append(f"   代码上下文: {ctx[:200]}")
    return "\n".join(lines)


def _build_user_prompt(
    file_path: str, strings: dict[str, str], contexts: dict[str, dict] | None,
) -> str:
    """构建用户 prompt"""
    crate_name = extract_crate_name(file_path)
    entries_text = _build_entries_text(strings, contexts)
    prompt = _USER_PROMPT_TEMPLATE.format(
        file_path=file_path, crate_name=crate_name, entries=entries_text,
    )
    input_json = {s: "" for s in strings}
    prompt += f"\n\n输入:\n```json\n{json.dumps(input_json, ensure_ascii=False)}\n```"
    return prompt


async def _call_ai(
    client: object, model: str, system_prompt: str, user_prompt: str,
) -> str:
    """调用 AI API，内置网络错误重试"""
    for attempt in range(5):
        try:
            response = await client.chat.completions.create(  # type: ignore[attr-defined]
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0,
                max_tokens=65535,
                extra_body={"thinking": {"type": "disabled"}},
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as e:
            if attempt < 4:
                delay = (2 ** attempt) * 3 + random.uniform(0, 2)
                log.debug("网络错误，等待 %.1fs 重试 (%d/5)", delay, attempt + 1)
                await asyncio.sleep(delay)
                continue
            raise
    return ""


async def _translate_batch(
    client: object,
    model: str,
    file_path: str,
    strings: dict[str, str],
    contexts: dict[str, dict] | None,
    system_prompt: str,
) -> dict[str, str]:
    """翻译一批字符串：JSON → XML(CDATA) → 编号格式 三级降级"""
    user_prompt = _build_user_prompt(file_path, strings, contexts)

    # 第一级: JSON 格式重试 3 次
    for attempt in range(3):
        try:
            raw = await _call_ai(client, model, system_prompt, user_prompt)
            result = parse_json_response(raw)
            if result:
                return result
        except Exception as e:
            log.warning("翻译失败 %s: %s", file_path, e)
            return {}

    # 第二级: XML(CDATA) 格式重试 3 次
    xml_prompt = user_prompt + _XML_FALLBACK_INSTRUCTION
    for attempt in range(3):
        try:
            raw = await _call_ai(client, model, system_prompt, xml_prompt)
            result = parse_xml_response(raw)
            if result:
                return result
            log.debug("XML 解析重试 (%d/3): %s", attempt + 1, file_path)
        except Exception as e:
            log.warning("翻译失败 %s: %s", file_path, e)
            return {}

    # 第三级: 编号格式重试 3 次
    keys = list(strings.keys())
    numbered_prompt = user_prompt + _build_numbered_instruction(len(keys))
    for attempt in range(3):
        try:
            raw = await _call_ai(client, model, system_prompt, numbered_prompt)
            result = parse_numbered_response(raw, keys)
            if result:
                return result
            log.debug("编号格式解析重试 (%d/3): %s", attempt + 1, file_path)
        except Exception as e:
            log.warning("翻译失败 %s: %s", file_path, e)
            return {}

    log.warning(
        "[FAILED] JSON+XML+编号 均失败: %s (%d 条)", file_path, len(strings),
    )
    return {}


def _split_batch(
    strings: dict[str, str], max_size: int = 150,
) -> list[dict[str, str]]:
    """将大字典拆分为多个小批次"""
    items = list(strings.items())
    return [
        dict(items[i : i + max_size]) for i in range(0, len(items), max_size)
    ]


async def _translate_async(
    all_strings: TranslationDict,
    existing: TranslationDict,
    all_contexts: dict[str, dict] | None,
    mode: str,
    lang: str,
    glossary_path: str,
    ai_cfg: AIConfig,
) -> TranslationDict:
    """异步并发翻译"""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(base_url=ai_cfg.base_url, api_key=ai_cfg.api_key)
    semaphore = asyncio.Semaphore(ai_cfg.concurrency)

    glossary_section = build_glossary_section(glossary_path)
    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(
        lang=lang, glossary_section=glossary_section,
    )

    result: TranslationDict = {fp: dict(v) for fp, v in existing.items()}
    tasks: list[asyncio.Task] = []

    for file_path, strings in all_strings.items():
        to_translate: dict[str, str] = {}
        if file_path not in result:
            result[file_path] = {}
        for s in strings:
            if mode == "full" or not result.get(file_path, {}).get(s):
                to_translate[s] = ""
        if not to_translate:
            continue
        file_contexts = all_contexts.get(file_path) if all_contexts else None
        for batch in _split_batch(to_translate):
            async def do_batch(
                fp: str = file_path, b: dict = batch, ctx: dict | None = file_contexts,
            ) -> tuple[str, dict[str, str]]:
                async with semaphore:
                    return fp, await _translate_batch(
                        client, ai_cfg.model, fp, b, ctx, system_prompt,
                    )
            tasks.append(asyncio.create_task(do_batch()))

    total = len(tasks)
    log.info("共 %d 个翻译批次，并发数 %d", total, ai_cfg.concurrency)
    pbar = ProgressBar(total, desc="翻译")

    fail_count = 0
    for coro in asyncio.as_completed(tasks):
        fp, translations = await coro
        if translations:
            result.setdefault(fp, {}).update(translations)
        else:
            fail_count += 1
        pbar.update(extra=f"失败 {fail_count}")
    pbar.finish()

    return result


def translate_all(
    strings_path: str, output_path: str, context_path: str = "",
    glossary_path: str = "config/glossary.yaml", mode: str = "incremental",
    lang: str = "zh-CN", ai_cfg: AIConfig | None = None,
) -> None:
    """同步入口"""
    if ai_cfg is None:
        ai_cfg = AIConfig()
    ai_cfg.validate()

    all_strings: TranslationDict = load_json(strings_path)
    existing = load_json(output_path) if Path(output_path).exists() else {}
    all_contexts = (
        load_json(context_path)
        if context_path and Path(context_path).exists()
        else None
    )

    result = asyncio.run(_translate_async(
        all_strings, existing, all_contexts,
        mode, lang, glossary_path, ai_cfg,
    ))
    save_json(result, output_path)
    log.info("翻译结果已保存: %s", output_path)


def run(args: argparse.Namespace) -> None:
    """CLI 入口"""
    ai_cfg = AIConfig(
        base_url=args.base_url, api_key=args.api_key,
        model=args.model, concurrency=args.concurrency,
    )
    translate_all(
        args.input, args.output, args.context,
        args.glossary, args.mode, args.lang, ai_cfg,
    )
