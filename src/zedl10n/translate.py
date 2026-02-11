"""AI 并发翻译，内置智能过滤"""

from __future__ import annotations

import argparse
import asyncio
import logging
import random
from pathlib import Path

from .prompts import (
    SYSTEM_PROMPT_TEMPLATE, XML_FALLBACK_INSTRUCTION,
    build_fix_prompt, build_numbered_instruction,
    build_user_prompt, estimate_tokens, validate_placeholders,
)
from .utils import (
    AIConfig, ProgressBar, TranslationDict,
    build_glossary_section, load_json,
    parse_json_response, parse_numbered_response,
    parse_xml_response, save_json,
)

log = logging.getLogger(__name__)


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
        "[FAILED] JSON+XML+编号 均失败: %s (%d 条)", file_path, len(strings),
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


MAX_INPUT_TOKENS = 140_000


def _estimate_request_tokens(
    system_prompt: str, file_path: str,
    strings: dict[str, str], file_content: str,
) -> int:
    """估算完整请求（system + user prompt）的 token 数"""
    user_prompt = build_user_prompt(file_path, strings, file_content)
    return estimate_tokens(system_prompt) + estimate_tokens(user_prompt)


def _truncate_file_content(
    file_content: str, strings: dict[str, str],
    system_prompt: str, max_tokens: int,
) -> str:
    """当源文件过大时，保留字符串附近上下文并截断其余部分"""
    budget = max_tokens - estimate_tokens(system_prompt) - 5000
    if budget <= 0:
        return ""
    if estimate_tokens(file_content) <= budget:
        return file_content

    # 找到每个字符串在文件中的行号（匹配带引号的字面量）
    lines = file_content.split("\n")
    hit_lines: set[int] = set()
    for s in strings:
        quoted = f'"{s}"'
        for i, line in enumerate(lines):
            if quoted in line:
                hit_lines.add(i)

    if not hit_lines:
        # 没找到匹配，按比例从头截断
        ratio = budget / estimate_tokens(file_content)
        cut = int(len(file_content) * ratio)
        return file_content[:cut] + "\n... (文件过大，已截断)"

    # 从大窗口开始尝试，逐步缩小直到满足 budget
    for ctx_lines in (80, 40, 20, 10):
        kept = _build_context_regions(lines, hit_lines, ctx_lines)
        if estimate_tokens(kept) <= budget:
            log.debug(
                "源文件过大，保留 %d 处字符串附近 ±%d 行上下文",
                len(hit_lines), ctx_lines,
            )
            return kept

    # 最小窗口仍超限，用最小窗口的结果再按比例截断
    kept = _build_context_regions(lines, hit_lines, 5)
    if estimate_tokens(kept) > budget:
        ratio = budget / estimate_tokens(kept)
        cut = int(len(kept) * ratio)
        kept = kept[:cut] + "\n... (已截断)"
    return kept


def _build_context_regions(
    lines: list[str], hit_lines: set[int], ctx: int,
) -> str:
    """围绕命中行构建上下文区域，合并重叠区间"""
    total = len(lines)
    # 构建区间 [start, end)
    intervals: list[tuple[int, int]] = []
    for ln in sorted(hit_lines):
        intervals.append((max(0, ln - ctx), min(total, ln + ctx + 1)))

    # 合并重叠区间
    merged: list[tuple[int, int]] = []
    for start, end in intervals:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    # 拼接各区域
    parts: list[str] = []
    for i, (start, end) in enumerate(merged):
        if i == 0 and start > 0:
            parts.append(f"// ... (省略第 1-{start} 行)")
        elif i > 0:
            prev_end = merged[i - 1][1]
            parts.append(f"// ... (省略第 {prev_end+1}-{start} 行)")
        parts.append("\n".join(lines[start:end]))
    if merged[-1][1] < total:
        parts.append(f"// ... (省略第 {merged[-1][1]+1}-{total} 行)")

    return "\n".join(parts)


def _split_batch(
    strings: dict[str, str],
    system_prompt: str,
    file_path: str,
    file_content: str,
    max_tokens: int = MAX_INPUT_TOKENS,
) -> tuple[list[dict[str, str]], str]:
    """根据 token 预算将字符串拆分为多批。

    如果源文件过大，自动截断。返回 (批次列表, 实际使用的 file_content)。
    """
    # 源文件过大时智能截断（保留字符串附近上下文）
    content = _truncate_file_content(
        file_content, strings, system_prompt, max_tokens,
    )

    items = list(strings.items())
    # 先尝试全部放一批
    total = _estimate_request_tokens(
        system_prompt, file_path, dict(items), content,
    )
    if total <= max_tokens:
        return [dict(items)], content

    # 超限：估算每条字符串的平均 token 开销，计算初始批容量
    overhead = _estimate_request_tokens(
        system_prompt, file_path, {}, content,
    )
    per_string = max(1, (total - overhead) // len(items))
    capacity = max(10, (max_tokens - overhead) // per_string)

    # 验证并缩减直到满足限制
    while capacity >= 10:
        test_batch = dict(items[:capacity])
        tokens = _estimate_request_tokens(
            system_prompt, file_path, test_batch, content,
        )
        if tokens <= max_tokens:
            break
        capacity = int(capacity * 0.8)
    capacity = max(10, capacity)

    batches = [
        dict(items[i : i + capacity])
        for i in range(0, len(items), capacity)
    ]
    return batches, content


def _read_source_file(file_path: str, source_root: str) -> str:
    """读取源文件内容，找不到则返回空字符串"""
    if not source_root:
        return ""
    root = Path(source_root)
    candidates = [root / file_path]
    # 如果 file_path 以 "zed/" 开头，也尝试去掉前缀
    if file_path.startswith("zed/"):
        candidates.append(root / file_path[4:])
    for p in candidates:
        if p.exists():
            try:
                return p.read_text(encoding="utf-8")
            except Exception:
                return ""
    return ""


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
        lang=lang, glossary_section=glossary_section,
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
        batches, file_content = _split_batch(
            to_translate, system_prompt, file_path, raw_content,
        )
        for batch in batches:
            async def do_batch(
                fp: str = file_path, b: dict = batch, fc: str = file_content,
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

    return result


def translate_all(
    strings_path: str, output_path: str, context_path: str = "",
    glossary_path: str = "config/glossary.yaml", mode: str = "incremental",
    lang: str = "zh-CN", ai_cfg: AIConfig | None = None,
    source_root: str = "",
) -> None:
    """同步入口"""
    if ai_cfg is None:
        ai_cfg = AIConfig()
    ai_cfg.validate()

    all_strings: TranslationDict = load_json(strings_path)
    existing = load_json(output_path) if Path(output_path).exists() else {}

    result = asyncio.run(_translate_async(
        all_strings, existing,
        mode, lang, glossary_path, ai_cfg, source_root,
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
        source_root=getattr(args, "source_root", ""),
    )
