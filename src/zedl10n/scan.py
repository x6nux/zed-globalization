"""AI 扫描识别需翻译的 .rs 文件"""

from __future__ import annotations

import argparse
import asyncio
import logging
import random
from pathlib import Path

from .utils import AIConfig, ProgressBar

log = logging.getLogger(__name__)

# AI 分析提示词
_SYSTEM_PROMPT = """你是一个代码分析助手。你需要判断给定的 Rust 源文件是否包含需要翻译的用户界面字符串。

判断标准：
- 包含菜单项、按钮文本、提示信息、错误消息、对话框文本等面向用户的字符串 → 需要翻译
- 仅包含内部标识符、日志格式、测试断言、API 路径、文件路径等 → 不需要翻译

请只回答 YES 或 NO，并在下一行给出简短理由（不超过 20 字）。"""

_USER_PROMPT_TEMPLATE = """文件路径: {path}

```rust
{content}
```

这个文件是否包含需要翻译的 UI 字符串？"""


def find_all_rs_files(source_root: str | Path) -> list[Path]:
    """递归查找所有 .rs 文件"""
    root = Path(source_root) / "crates"
    if not root.exists():
        log.warning("crates 目录不存在: %s", root)
        return []
    files = sorted(root.rglob("*.rs"))
    log.info("共找到 %d 个 .rs 文件", len(files))
    return files


def _split_content(content: str, max_chars: int = 8000) -> list[str]:
    """超大文件自动分割成多段"""
    if len(content) <= max_chars:
        return [content]
    chunks: list[str] = []
    lines = content.splitlines(keepends=True)
    current: list[str] = []
    current_len = 0
    for line in lines:
        if current_len + len(line) > max_chars and current:
            chunks.append("".join(current))
            current = []
            current_len = 0
        current.append(line)
        current_len += len(line)
    if current:
        chunks.append("".join(current))
    return chunks


def _read_file(fp: Path) -> str | None:
    """读取文件内容，空文件或读取失败返回 None"""
    try:
        content = fp.read_text(encoding="utf-8", errors="ignore")
    except OSError as e:
        log.warning("读取失败 %s: %s", fp, e)
        return None
    return content if content.strip() else None


async def _analyze_file(
    client: object,
    model: str,
    file_path: Path,
    content: str,
    source_root: str,
    max_retries: int = 5,
) -> bool | None:
    """调用 AI 分析单个文件是否需要翻译，返回 None 表示失败"""
    rel_path = file_path.relative_to(source_root)
    chunks = _split_content(content)

    for chunk in chunks:
        prompt = _USER_PROMPT_TEMPLATE.format(path=rel_path, content=chunk)
        for attempt in range(max_retries):
            try:
                response = await client.chat.completions.create(  # type: ignore[attr-defined]
                    model=model,
                    messages=[
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0,
                    max_tokens=65535,
                    extra_body={"thinking": {"type": "disabled"}},
                )
                answer = response.choices[0].message.content or ""
                answer = answer.strip()
                if answer.upper().startswith("YES"):
                    log.debug("需要翻译: %s — %s", rel_path, answer)
                    return True
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    delay = (2 ** attempt) * 3 + random.uniform(0, 2)
                    log.debug("错误，%s 等待 %.1fs 重试 (%d/%d)",
                              rel_path, delay, attempt + 1, max_retries)
                    await asyncio.sleep(delay)
                    continue
                log.warning("分析文件失败（已重试%d次）%s: %s",
                            max_retries, rel_path, e)
                return None

    log.debug("无需翻译: %s", rel_path)
    return False


async def _scan_async(
    source_root: str, ai_cfg: AIConfig
) -> list[str]:
    """异步并发扫描所有文件（含二轮重试机制）"""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(base_url=ai_cfg.base_url, api_key=ai_cfg.api_key)
    semaphore = asyncio.Semaphore(ai_cfg.concurrency)
    all_files = find_all_rs_files(source_root)
    results: list[str] = []
    yes_count = 0
    pbar = ProgressBar(len(all_files), desc="扫描")

    async def check(fp: Path) -> bool | None:
        nonlocal yes_count
        async with semaphore:
            content = _read_file(fp)
            if content is None:
                pbar.update(extra=f"发现 {yes_count} 个待翻译")
                return False
            result = await _analyze_file(
                client, ai_cfg.model, fp, content, source_root,
            )
            if result is True:
                yes_count += 1
            pbar.update(extra=f"发现 {yes_count} 个待翻译")
            return result

    done = await asyncio.gather(*[check(fp) for fp in all_files])
    pbar.finish()

    failed_files: list[Path] = []
    for fp, r in zip(all_files, done):
        if r is True:
            results.append(str(fp))
        elif r is None:
            failed_files.append(fp)

    # 二轮重试：等待 60s 后对失败文件逐个重试 10 次
    if failed_files:
        log.info("等待 60s 后重试 %d 个失败文件...", len(failed_files))
        await asyncio.sleep(60)
        results.extend(await _retry_failed(
            client, ai_cfg, semaphore, failed_files, source_root,
        ))

    return results


async def _retry_failed(
    client: object, ai_cfg: AIConfig, semaphore: asyncio.Semaphore,
    failed_files: list[Path], source_root: str,
) -> list[str]:
    """二轮重试失败文件，每个最多 10 次，仍失败则默认为待翻译"""
    recovered: list[str] = []
    retry_yes = 0
    pbar = ProgressBar(len(failed_files), desc="重试")

    async def retry(fp: Path) -> bool:
        nonlocal retry_yes
        async with semaphore:
            content = _read_file(fp)
            if content is None:
                pbar.update(extra=f"恢复 {retry_yes} 个")
                return True  # 读取失败，默认为待翻译
            result = await _analyze_file(
                client, ai_cfg.model, fp, content, source_root,
                max_retries=10,
            )
            if result is None:
                rel = fp.relative_to(source_root)
                log.warning("重试仍失败，默认为待翻译: %s", rel)
                result = True
            if result:
                retry_yes += 1
            pbar.update(extra=f"恢复 {retry_yes} 个")
            return result

    retry_done = await asyncio.gather(*[retry(fp) for fp in failed_files])
    pbar.finish()

    for fp, r in zip(failed_files, retry_done):
        if r:
            recovered.append(str(fp))
    return recovered


def scan_files(source_root: str, ai_cfg: AIConfig) -> list[str]:
    """同步入口，返回需要翻译的文件路径列表"""
    ai_cfg.validate()
    return asyncio.run(_scan_async(source_root, ai_cfg))


def run(args: argparse.Namespace) -> None:
    """CLI 入口"""
    ai_cfg = AIConfig(
        base_url=args.base_url,
        api_key=args.api_key,
        model=args.model,
        concurrency=args.concurrency,
    )
    files = scan_files(args.source_root, ai_cfg)
    log.info("扫描完成，共 %d 个文件需要翻译", len(files))
    for f in files:
        print(f)
