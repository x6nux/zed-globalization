"""AI 扫描识别需翻译的 .rs 文件（支持全量 / 增量两种模式）"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import random
from pathlib import Path
from typing import Any

from .utils import AIConfig, ProgressBar

log = logging.getLogger(__name__)

# --- 扫描结果持久化格式 ---
# {"version": "v0.175.0", "files": ["crates/editor/src/editor.rs", ...]}
ScanResult = dict[str, Any]

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


async def _scan_file_list(
    file_list: list[Path],
    source_root: str,
    ai_cfg: AIConfig,
    desc: str = "扫描",
) -> list[str]:
    """对指定文件列表做 AI 扫描，返回需要翻译的文件路径（含二轮重试）"""
    from openai import AsyncOpenAI

    if not file_list:
        return []

    client = AsyncOpenAI(base_url=ai_cfg.base_url, api_key=ai_cfg.api_key)
    semaphore = asyncio.Semaphore(ai_cfg.concurrency)
    results: list[str] = []
    yes_count = 0
    pbar = ProgressBar(len(file_list), desc=desc)

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

    done = await asyncio.gather(*[check(fp) for fp in file_list])
    pbar.finish()

    failed_files: list[Path] = []
    for fp, r in zip(file_list, done):
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


async def _scan_async(
    source_root: str, ai_cfg: AIConfig
) -> list[str]:
    """全量扫描所有 .rs 文件"""
    all_files = find_all_rs_files(source_root)
    return await _scan_file_list(all_files, source_root, ai_cfg, desc="全量扫描")


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
    """全量扫描，返回需要翻译的文件路径列表（绝对路径）"""
    ai_cfg.validate()
    return asyncio.run(_scan_async(source_root, ai_cfg))


# ---- 增量扫描 ----

def load_scan_result(path: str | Path) -> ScanResult:
    """读取上次扫描结果，不存在或解析失败返回空结果"""
    p = Path(path)
    if not p.exists():
        return {"version": "", "files": []}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "files" in data:
            return data
    except (json.JSONDecodeError, OSError) as e:
        log.warning("读取上次扫描结果失败 %s: %s", path, e)
    return {"version": "", "files": []}


def save_scan_result(
    path: str | Path, version: str, files: list[str],
) -> None:
    """保存扫描结果"""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    data: ScanResult = {"version": version, "files": sorted(files)}
    Path(path).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    log.info("扫描结果已保存: %s (版本 %s, %d 个文件)", path, version, len(files))


def scan_incremental(
    source_root: str,
    ai_cfg: AIConfig,
    changed_files: list[str],
    deleted_files: list[str],
    previous_files: list[str],
) -> list[str]:
    """增量扫描：只 AI 分析变化的文件，合并上次结果。

    所有路径均为相对于 source_root 的相对路径。

    合并逻辑:
        新结果 = (previous - deleted - changed) + 新扫描中判定为 YES 的
    """
    ai_cfg.validate()

    # 只关注 .rs 文件
    changed_rs = [f for f in changed_files if f.endswith(".rs")]
    deleted_set = set(deleted_files)
    changed_set = set(changed_rs)

    if not changed_rs:
        log.info("没有变化的 .rs 文件需要扫描")
        kept = [f for f in previous_files if f not in deleted_set]
        return kept

    log.info(
        "增量扫描: %d 个变化文件, %d 个删除文件, 上次 %d 个文件",
        len(changed_rs), len(deleted_files), len(previous_files),
    )

    # 构建绝对路径列表给扫描引擎
    root = Path(source_root)
    abs_files = [root / f for f in changed_rs if (root / f).exists()]
    if not abs_files:
        log.warning("变化文件均不存在于源码中，跳过扫描")
        kept = [f for f in previous_files if f not in deleted_set]
        return kept

    # AI 扫描变化的文件
    newly_yes_abs = asyncio.run(
        _scan_file_list(abs_files, source_root, ai_cfg, desc="增量扫描"),
    )
    # 转回相对路径
    newly_yes = {str(Path(f).relative_to(root)) for f in newly_yes_abs}

    # 合并：保留未变化的 + 新扫描通过的
    kept = [
        f for f in previous_files
        if f not in deleted_set and f not in changed_set
    ]
    merged = sorted(set(kept) | newly_yes)

    log.info(
        "增量合并完成: 保留 %d + 新增 %d = 共 %d 个待翻译文件",
        len(kept), len(newly_yes), len(merged),
    )
    return merged


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
