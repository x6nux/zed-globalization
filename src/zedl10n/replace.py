"""替换 Zed 源码中的字符串"""

from __future__ import annotations

import argparse
import logging
import re
from pathlib import Path

from .utils import TranslationDict, extract_placeholders, load_json, save_json

log = logging.getLogger(__name__)

# 纯 ASCII 标点/空白字符串——替换它们会破坏 Rust 语法
_PUNCT_ONLY = re.compile(r'^[\s\x20-\x2f\x3a-\x40\x5b-\x60\x7b-\x7e]+$')

# 纯小写 ASCII 标识符（含连字符/下划线）——键名、枚举值、内部标识符
# 如 "backspace", "delete", "ctrl-alt-delete", "delete_path"
_ASCII_IDENTIFIER = re.compile(r'^[a-z][a-z0-9_-]*$')

# 中文标点 → ASCII 标点映射（修复字符串之间被误替换的分隔符）
_ZH_PUNCT_BETWEEN_STRINGS = re.compile(r'(?<=\w")\s*[、，]\s*(?=")')
_ZH_SEMICOLON_BETWEEN_STRINGS = re.compile(r'(?<=\w")\s*[；]\s*(?=")')

# 不可替换区域：字节字符串 + 属性宏
# 字节字符串: br##"..."##, br#"..."#, br"...", b"..."
# 属性宏: #[action(...)], #[serde(...)], #[derive(...)] 等
# 注意: #[error("...")] 包含用户可见的错误消息，不应被保护
_PROTECTED_RE = re.compile(
    r'br(#+)".*?"\1'               # br#"..."#
    r'|br"(?:[^"\\]|\\.)*"'        # br"..."
    r'|b"(?:[^"\\]|\\.)*"'         # b"..."
    r'|#\[(?!error\b)[\w:]+\([^]]*?\)\]',  # #[attr(...)]（排除 #[error]）
    re.DOTALL,
)


def _is_positional(ph: str) -> bool:
    """判断占位符是否按位置绑定参数。

    位置绑定（顺序敏感）：{}, {:?}, {:.2}, %s, %d 等
    命名/索引（顺序无关）：{name}, {0}, {name:?} 等
    """
    if ph.startswith("%"):
        return True
    inner = ph[1:-1]  # 去掉 { }
    return inner == "" or inner.startswith(":")


def _check_placeholders(src: list[str], dst: list[str]) -> bool:
    """校验占位符兼容性。

    - 位置绑定占位符（{}, {:?} 等）：顺序必须严格一致
    - 命名/索引占位符（{name}, {0} 等）：只需集合一致，顺序随意
    """
    src_pos = [p for p in src if _is_positional(p)]
    dst_pos = [p for p in dst if _is_positional(p)]
    if src_pos != dst_pos:
        return False
    src_named = sorted(p for p in src if not _is_positional(p))
    dst_named = sorted(p for p in dst if not _is_positional(p))
    return src_named == dst_named


def _filter_replacements(
    replacements: dict[str, str], file_path: str,
) -> dict[str, str]:
    """第 2 层：过滤会破坏 Rust 语法的翻译条目"""
    clean: dict[str, str] = {}
    for original, new_value in replacements.items():
        if not new_value:
            clean[original] = new_value
            continue
        # 纯标点/空白字符串不应被翻译（如 ", " → "、" 会破坏数组语法）
        if _PUNCT_ONLY.match(original):
            log.debug("跳过纯标点: %r → %r (%s)", original, new_value, file_path)
            continue
        # 纯小写标识符不应被替换（键名、枚举值等：backspace, delete, tab）
        if _ASCII_IDENTIFIER.match(original):
            log.debug("跳过标识符: %r → %r (%s)", original, new_value, file_path)
            continue
        # 占位符兜底校验
        src_ph = extract_placeholders(original)
        dst_ph = extract_placeholders(new_value)
        if not _check_placeholders(src_ph, dst_ph):
            log.warning(
                "占位符不匹配，跳过: %r → %r (原文=%s, 译文=%s) [%s]",
                original, new_value, src_ph, dst_ph, file_path,
            )
            continue
        clean[original] = new_value
    return clean


def _sanitize_rust_syntax(content: str) -> str:
    """第 3 层：修复替换后破坏 Rust 语法的中文标点

    例如 "文本"、"文本" → "文本", "文本"
    利用 \\w" 判断前一个引号是字符串结尾，避免误改 "、" 字符串字面量。
    """
    content = _ZH_PUNCT_BETWEEN_STRINGS.sub(', ', content)
    content = _ZH_SEMICOLON_BETWEEN_STRINGS.sub('; ', content)
    return content


def _find_protected_ranges(content: str) -> list[tuple[int, int]]:
    """查找文件中所有不可替换区域（字节字符串 + 属性宏）的位置范围"""
    return [(m.start(), m.end()) for m in _PROTECTED_RE.finditer(content)]


def _replace_skip_protected(
    content: str, old_text: str, new_text: str,
    protected: list[tuple[int, int]],
) -> tuple[str, int]:
    """替换字符串，自动跳过受保护区域（字节字符串、属性宏等）"""
    if not protected:
        count = content.count(old_text)
        return content.replace(old_text, new_text), count

    parts: list[str] = []
    count = 0
    pos = 0
    while True:
        idx = content.find(old_text, pos)
        if idx == -1:
            parts.append(content[pos:])
            break
        parts.append(content[pos:idx])
        if any(s <= idx < e for s, e in protected):
            parts.append(old_text)  # 在受保护区域内，保持原样
        else:
            parts.append(new_text)
            count += 1
        pos = idx + len(old_text)
    return ''.join(parts), count


def _resolve_file_path(file_path: str, root: Path) -> Path | None:
    """多策略解析文件路径，找不到返回 None。

    优先级:
      1. 绝对路径直接使用
      2. 相对路径直接存在
      3. source_root / file_path
      4. 去掉与 source_root 重复的前缀（如 zed/zed/... → zed/...）
    """
    p = Path(file_path)

    # 1) 绝对路径
    if p.is_absolute() and p.exists():
        return p

    # 2) 相对路径直接存在
    if p.exists():
        return p

    # 3) source_root / file_path
    fp = root / file_path
    if fp.exists():
        return fp

    # 4) 去掉重复的 source_root 目录名前缀
    try:
        rel = p.relative_to(root.name)
        fp = root / rel
        if fp.exists():
            return fp
    except ValueError:
        pass

    log.warning("文件不存在，跳过: %s", file_path)
    return None


def replace_in_source(
    translations: TranslationDict, source_root: str = "."
) -> int:
    """将翻译替换到源码中，返回替换总数"""
    root = Path(source_root)
    total_count = 0
    missing_files: list[str] = []

    for file_path, raw_replacements in translations.items():
        fp = _resolve_file_path(file_path, root)
        if fp is None:
            missing_files.append(file_path)
            continue

        try:
            content = fp.read_text(encoding="utf-8")
        except OSError as e:
            log.warning("读取失败 %s: %s", fp, e)
            continue

        replacements = _filter_replacements(raw_replacements, file_path)
        protected = _find_protected_ranges(content)

        count = 0
        for original, new_value in replacements.items():
            if not new_value:
                continue
            # 确保译文中的双引号被转义为 \"，防止破坏 Rust 字符串语法
            safe_value = new_value.replace('\\"', '"').replace('"', '\\"')
            old_text = f'"{original}"'
            new_text = f'"{safe_value}"'
            new_content, n = _replace_skip_protected(
                content, old_text, new_text, protected,
            )
            if n > 0:
                count += n
                content = new_content
                # 替换可能导致位置偏移，需重新计算受保护区域范围
                if protected:
                    protected = _find_protected_ranges(content)

        if count > 0:
            content = _sanitize_rust_syntax(content)
            fp.write_text(content, encoding="utf-8")
            log.debug("替换 %d 处: %s", count, fp)
            total_count += count

    if missing_files:
        log.warning("以下 %d 个文件在源码中不存在:", len(missing_files))
        for f in missing_files[:10]:
            log.warning("  %s", f)

    log.info("替换完成: 共 %d 处", total_count)
    return total_count, missing_files


def _cleanup_translation_json(
    input_path: str, missing_files: list[str],
) -> None:
    """从翻译 JSON 中删除源码中不存在的文件条目并回写"""
    if not missing_files:
        return
    data: TranslationDict = load_json(input_path)
    removed = 0
    for fp in missing_files:
        if fp in data:
            del data[fp]
            removed += 1
    if removed:
        save_json(data, input_path)
        log.info("已从翻译文件中清理 %d 个不存在的文件条目", removed)


def run(args: argparse.Namespace) -> None:
    """CLI 入口"""
    translations: TranslationDict = load_json(args.input)
    _, missing = replace_in_source(translations, args.source_root)
    _cleanup_translation_json(args.input, missing)
