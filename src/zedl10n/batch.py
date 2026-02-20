"""翻译批次拆分与 token 预算管理"""

from __future__ import annotations

import logging

from .prompts import build_user_prompt, estimate_tokens

log = logging.getLogger(__name__)

MAX_INPUT_TOKENS = 50_000


def estimate_request_tokens(
    system_prompt: str,
    file_path: str,
    strings: dict[str, str],
    file_content: str,
) -> int:
    """估算完整请求（system + user prompt）的 token 数"""
    user_prompt = build_user_prompt(file_path, strings, file_content)
    return estimate_tokens(system_prompt) + estimate_tokens(user_prompt)


def truncate_file_content(
    file_content: str,
    strings: dict[str, str],
    system_prompt: str,
    max_tokens: int,
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
                len(hit_lines),
                ctx_lines,
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
    lines: list[str],
    hit_lines: set[int],
    ctx: int,
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
            parts.append(f"// ... (省略第 {prev_end + 1}-{start} 行)")
        parts.append("\n".join(lines[start:end]))
    if merged[-1][1] < total:
        parts.append(f"// ... (省略第 {merged[-1][1] + 1}-{total} 行)")

    return "\n".join(parts)


def split_batch(
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
    content = truncate_file_content(
        file_content,
        strings,
        system_prompt,
        max_tokens,
    )

    items = list(strings.items())
    # 先尝试全部放一批
    total = estimate_request_tokens(
        system_prompt,
        file_path,
        dict(items),
        content,
    )
    if total <= max_tokens:
        return [dict(items)], content

    # 超限：估算每条字符串的平均 token 开销，计算初始批容量
    overhead = estimate_request_tokens(
        system_prompt,
        file_path,
        {},
        content,
    )
    per_string = max(1, (total - overhead) // len(items))
    capacity = max(10, (max_tokens - overhead) // per_string)

    # 验证并缩减直到满足限制
    while capacity >= 10:
        test_batch = dict(items[:capacity])
        tokens = estimate_request_tokens(
            system_prompt,
            file_path,
            test_batch,
            content,
        )
        if tokens <= max_tokens:
            break
        capacity = int(capacity * 0.8)
    capacity = max(10, capacity)

    batches = [dict(items[i : i + capacity]) for i in range(0, len(items), capacity)]
    return batches, content
