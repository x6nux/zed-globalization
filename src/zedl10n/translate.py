"""AI 并发翻译，内置智能过滤"""

from __future__ import annotations

import argparse
import asyncio
import logging
import random
from pathlib import Path

from .batch import split_batch
from .prompts import (
    SYSTEM_PROMPT_TEMPLATE,
    XML_FALLBACK_INSTRUCTION,
    build_consistency_fix_prompt,
    build_fix_prompt,
    build_numbered_instruction,
    build_user_prompt,
    validate_placeholders,
)
from .utils import (
    AIConfig,
    ProgressBar,
    TranslationDict,
    build_glossary_section,
    load_json,
    normalize_fullwidth,
    parse_json_response,
    parse_numbered_response,
    parse_xml_response,
    save_json,
)

log = logging.getLogger(__name__)


async def _call_ai(
    client: object,
    model: str,
    system_prompt: str,
    user_prompt: str,
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
                delay = (2**attempt) * 3 + random.uniform(0, 2)
                log.debug("网络错误，等待 %.1fs 重试 (%d/5)", delay, attempt + 1)
                await asyncio.sleep(delay)
                continue
            raise
    return ""


async def _fetch_translation(
    client: object,
    model: str,
    file_path: str,
    strings: dict[str, str],
    file_content: str,
    system_prompt: str,
) -> dict[str, str]:
    """通过 JSON → XML(CDATA) → 编号格式 三级降级获取翻译结果"""
    user_prompt = build_user_prompt(file_path, strings, file_content)

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
    xml_prompt = user_prompt + XML_FALLBACK_INSTRUCTION
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
    numbered_prompt = user_prompt + build_numbered_instruction(len(keys))
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
        "[FAILED] JSON+XML+编号 均失败: %s (%d 条)",
        file_path,
        len(strings),
    )
    return {}


async def _translate_batch(
    client: object,
    model: str,
    file_path: str,
    strings: dict[str, str],
    file_content: str,
    system_prompt: str,
) -> dict[str, str]:
    """翻译一批字符串，含占位符校验和自动重试"""
    result = await _fetch_translation(
        client, model, file_path, strings, file_content, system_prompt,
    )
    if not result:
        return result

    # 占位符校验 + 重试（最多 2 次）
    for retry in range(2):
        errors = validate_placeholders(result)
        if not errors:
            return result
        log.debug(
            "占位符不匹配 %d 条，重试修正 (%d/2): %s",
            len(errors), retry + 1, file_path,
        )
        fix_prompt = build_fix_prompt(errors, result)
        try:
            raw = await _call_ai(client, model, system_prompt, fix_prompt)
            fixed = parse_json_response(raw)
        except Exception as e:
            log.warning("占位符修正请求失败 %s: %s", file_path, e)
            break
        if fixed:
            for key, val in fixed.items():
                if key in result:
                    result[key] = val

    # 最终校验：仍有问题的条目丢弃为空字符串
    final_errors = validate_placeholders(result)
    for original, (src_ph, dst_ph) in final_errors.items():
        log.warning(
            "占位符校验失败，丢弃译文: %r (原文占位符=%s, 译文占位符=%s) [%s]",
            original, src_ph, dst_ph, file_path,
        )
        result[original] = ""

    return result


def _read_source_file(file_path: str, source_root: str) -> str:
    """读取源文件内容，找不到则返回空字符串"""
    if not source_root:
        return ""
    root = Path(source_root)
    candidates = [root / file_path]
    if file_path.startswith("zed/"):
        candidates.append(root / file_path[4:])
    for p in candidates:
        if p.exists():
            try:
                return p.read_text(encoding="utf-8")
            except Exception:
                return ""
    return ""


async def _ai_fix_consistency(
    client: object,
    model: str,
    system_prompt: str,
    result: TranslationDict,
    glossary_path: str,
) -> tuple[TranslationDict, list[str]]:
    """用 AI 修复一致性问题，返回 (修复后结果, 修复日志)"""
    from .consistency import build_issues_for_ai, check_consistency

    issues = check_consistency(result, glossary_path)
    if not issues:
        return result, []

    log.info("一致性检查发现 %d 个问题，调用 AI 修复", len(issues))
    incon, glossary_v, keep_v = build_issues_for_ai(issues, result)
    if not incon and not glossary_v and not keep_v:
        return result, []

    user_prompt = build_consistency_fix_prompt(incon, glossary_v, keep_v)

    fix_log: list[str] = []
    try:
        raw = await _call_ai(client, model, system_prompt, user_prompt)
        fixed = parse_json_response(raw)
    except Exception as e:
        log.warning("AI 一致性修复请求失败: %s", e)
        return result, fix_log

    if not fixed:
        log.warning("AI 一致性修复返回为空")
        return result, fix_log

    # 将 AI 修正结果应用到所有文件
    for original, new_translation in fixed.items():
        if not new_translation:
            continue
        applied = 0
        for pairs in result.values():
            if original in pairs and pairs[original]:
                if pairs[original] != new_translation:
                    pairs[original] = new_translation
                    applied += 1
        if applied:
            fix_log.append(
                f'AI 修复: "{original}" → "{new_translation}" '
                f"(更新 {applied} 处)",
            )

    return result, fix_log


async def _translate_async(
    all_strings: TranslationDict,
    existing: TranslationDict,
    mode: str,
    lang: str,
    glossary_path: str,
    ai_cfg: AIConfig,
    source_root: str = "",
) -> TranslationDict:
    """异步并发翻译"""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(base_url=ai_cfg.base_url, api_key=ai_cfg.api_key)
    semaphore = asyncio.Semaphore(ai_cfg.concurrency)

    glossary_section = build_glossary_section(glossary_path)
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        lang=lang,
        glossary_section=glossary_section,
    )

    result: TranslationDict = {fp: dict(v) for fp, v in existing.items()}
    tasks: list[asyncio.Task] = []

    for file_path, strings in all_strings.items():
        to_translate: dict[str, str] = {}
        if file_path not in result:
            result[file_path] = {}
        for s in strings:
            if mode == "full" or s not in result.get(file_path, {}):
                to_translate[s] = ""
        if not to_translate:
            continue
        raw_content = _read_source_file(file_path, source_root)
        batches, file_content = split_batch(
            to_translate, system_prompt, file_path, raw_content,
        )
        for batch in batches:

            async def do_batch(
                fp: str = file_path,
                b: dict = batch,
                fc: str = file_content,
            ) -> tuple[str, dict[str, str]]:
                async with semaphore:
                    return fp, await _translate_batch(
                        client, ai_cfg.model, fp, b, fc, system_prompt,
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

    # AI 一致性修复（最多 2 轮）
    for fix_round in range(2):
        result, ai_fix_log = await _ai_fix_consistency(
            client, ai_cfg.model, system_prompt, result, glossary_path,
        )
        for msg in ai_fix_log:
            log.info("一致性修复 (第 %d 轮): %s", fix_round + 1, msg)
        if not ai_fix_log:
            break

    return result


def translate_all(
    strings_path: str,
    output_path: str,
    context_path: str = "",
    glossary_path: str = "config/glossary.yaml",
    mode: str = "incremental",
    lang: str = "zh-CN",
    ai_cfg: AIConfig | None = None,
    source_root: str = "",
) -> None:
    """同步入口"""
    if ai_cfg is None:
        ai_cfg = AIConfig()
    ai_cfg.validate()

    all_strings: TranslationDict = load_json(strings_path)
    existing = load_json(output_path) if Path(output_path).exists() else {}

    result = asyncio.run(
        _translate_async(
            all_strings, existing, mode, lang,
            glossary_path, ai_cfg, source_root,
        )
    )
    # 全角 ASCII 符号统一转半角，避免破坏 Rust 源码语法
    for fp in result:
        for s, t in result[fp].items():
            if t:
                result[fp][s] = normalize_fullwidth(t)

    # 规则兜底：AI 修复后仍有问题的，用规则强制统一
    from .consistency import fix_consistency

    result, fix_log = fix_consistency(result, glossary_path)
    for msg in fix_log:
        log.info("规则兜底修复: %s", msg)

    save_json(result, output_path)
    log.info("翻译结果已保存: %s", output_path)


def run(args: argparse.Namespace) -> None:
    """CLI 入口"""
    ai_cfg = AIConfig(
        base_url=args.base_url,
        api_key=args.api_key,
        model=args.model,
        concurrency=args.concurrency,
    )
    translate_all(
        args.input,
        args.output,
        args.context,
        args.glossary,
        args.mode,
        args.lang,
        ai_cfg,
        source_root=getattr(args, "source_root", ""),
    )
