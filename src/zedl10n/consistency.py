"""翻译一致性检查与自动修复"""

from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass

from .utils import TranslationDict, load_yaml

log = logging.getLogger(__name__)


@dataclass
class Issue:
    """一致性问题"""

    kind: str  # "inconsistent" | "glossary_violation" | "keep_original_violation"
    original: str
    detail: str
    fix_value: str = ""


def check_consistency(
    translations: TranslationDict,
    glossary_path: str = "config/glossary.yaml",
) -> list[Issue]:
    """检查翻译一致性，返回问题列表"""
    issues: list[Issue] = []
    issues.extend(_check_cross_file_inconsistency(translations))

    glossary = _load_glossary(glossary_path)
    if glossary:
        terms = glossary.get("terms", {})
        keep_original = glossary.get("keep_original", [])
        issues.extend(_check_glossary_terms(translations, terms))
        issues.extend(_check_keep_original(translations, keep_original))

    return issues


def fix_consistency(
    translations: TranslationDict,
    glossary_path: str = "config/glossary.yaml",
) -> tuple[TranslationDict, list[str]]:
    """自动修复一致性问题，返回 (修复后翻译, 修复日志)"""
    fix_log: list[str] = []

    # 1. 统一跨文件不一致的翻译
    log_entries = _fix_cross_file_inconsistency(translations)
    fix_log.extend(log_entries)

    # 2. 术语表合规修复
    glossary = _load_glossary(glossary_path)
    if glossary:
        terms = glossary.get("terms", {})
        log_entries = _fix_glossary_terms(translations, terms)
        fix_log.extend(log_entries)

    return translations, fix_log


def _load_glossary(glossary_path: str) -> dict:
    """加载术语表，失败返回空字典"""
    from pathlib import Path

    if not Path(glossary_path).exists():
        return {}
    try:
        return load_yaml(glossary_path) or {}
    except Exception:
        return {}


def _check_cross_file_inconsistency(
    translations: TranslationDict,
) -> list[Issue]:
    """检查同一原文在不同文件中翻译不一致的情况"""
    # 收集每个原文的所有非空译文
    original_to_translations: dict[str, dict[str, list[str]]] = {}
    for fp, pairs in translations.items():
        for original, translated in pairs.items():
            if not translated:
                continue
            original_to_translations.setdefault(original, {})
            original_to_translations[original].setdefault(translated, [])
            original_to_translations[original][translated].append(fp)

    issues: list[Issue] = []
    for original, trans_map in original_to_translations.items():
        if len(trans_map) <= 1:
            continue
        # 找出出现次数最多的译文
        counter = Counter(
            {t: len(fps) for t, fps in trans_map.items()},
        )
        best, _ = counter.most_common(1)[0]
        for translated, fps in trans_map.items():
            if translated != best:
                issues.append(Issue(
                    kind="inconsistent",
                    original=original,
                    detail=(
                        f'"{original}" 有 {len(trans_map)} 种不同译文, '
                        f'将统一为 "{best}"'
                    ),
                    fix_value=best,
                ))
                break  # 一条原文只报一次

    return issues


def _fix_cross_file_inconsistency(
    translations: TranslationDict,
) -> list[str]:
    """修复跨文件不一致：统一为出现次数最多的译文"""
    # 收集每个原文的所有非空译文及出现次数
    original_to_counter: dict[str, Counter] = {}
    for pairs in translations.values():
        for original, translated in pairs.items():
            if not translated:
                continue
            original_to_counter.setdefault(original, Counter())
            original_to_counter[original][translated] += 1

    fix_log: list[str] = []
    for original, counter in original_to_counter.items():
        if len(counter) <= 1:
            continue
        best, _ = counter.most_common(1)[0]
        fixed_count = 0
        for fp, pairs in translations.items():
            if original in pairs and pairs[original] and pairs[original] != best:
                pairs[original] = best
                fixed_count += 1
        if fixed_count:
            fix_log.append(
                f'统一译文: "{original}" → "{best}" '
                f"(修复 {fixed_count} 处)",
            )

    return fix_log


def _check_glossary_terms(
    translations: TranslationDict,
    terms: dict[str, str],
) -> list[Issue]:
    """检查术语表中的术语是否在译文中被正确使用"""
    issues: list[Issue] = []
    for en_term, zh_term in terms.items():
        # 构建大小写不敏感的匹配模式（只匹配完整单词）
        pattern = re.compile(
            rf"\b{re.escape(en_term)}\b", re.IGNORECASE,
        )
        for fp, pairs in translations.items():
            for original, translated in pairs.items():
                if not translated:
                    continue
                # 如果原文包含该术语，且译文中出现了英文原词而非中文译词
                if pattern.search(original) and pattern.search(translated):
                    # 译文中不应出现英文原词（除非中文译词也包含英文）
                    if zh_term not in translated:
                        issues.append(Issue(
                            kind="glossary_violation",
                            original=original,
                            detail=(
                                f'译文中出现未翻译的术语 "{en_term}", '
                                f'应为 "{zh_term}"'
                            ),
                        ))
    return issues


def _fix_glossary_terms(
    translations: TranslationDict,
    terms: dict[str, str],
) -> list[str]:
    """修复译文中未翻译的术语表词汇"""
    fix_log: list[str] = []
    for en_term, zh_term in terms.items():
        pattern = re.compile(
            rf"\b{re.escape(en_term)}\b", re.IGNORECASE,
        )
        fixed_count = 0
        for pairs in translations.values():
            for original, translated in pairs.items():
                if not translated:
                    continue
                if pattern.search(original) and pattern.search(translated):
                    if zh_term not in translated:
                        new_val = pattern.sub(zh_term, translated)
                        if new_val != translated:
                            pairs[original] = new_val
                            fixed_count += 1
        if fixed_count:
            fix_log.append(
                f'术语替换: "{en_term}" → "{zh_term}" '
                f"(修复 {fixed_count} 处)",
            )

    return fix_log


def _check_keep_original(
    translations: TranslationDict,
    keep_original: list[str],
) -> list[Issue]:
    """检查 keep_original 列表中的词是否被错误翻译"""
    issues: list[Issue] = []
    for word in keep_original:
        pattern = re.compile(
            rf"\b{re.escape(word)}\b", re.IGNORECASE,
        )
        for fp, pairs in translations.items():
            for original, translated in pairs.items():
                if not translated:
                    continue
                if pattern.search(original) and not pattern.search(translated):
                    # 原文有这个词但译文没有 → 可能被错误翻译了
                    # 不一定是错误（可能整句重写了），只标记为潜在问题
                    issues.append(Issue(
                        kind="keep_original_violation",
                        original=original,
                        detail=(
                            f'专有名词 "{word}" 可能被错误翻译, '
                            f'应保留原文'
                        ),
                    ))
    return issues


def build_issues_for_ai(
    issues: list[Issue],
    translations: TranslationDict,
) -> tuple[list[dict], list[dict], list[dict]]:
    """将问题列表转换为 AI 修复 prompt 所需的结构化数据。

    返回 (inconsistent, glossary_violations, keep_original_violations)。
    """
    inconsistent: list[dict] = []
    glossary_violations: list[dict] = []
    keep_original_violations: list[dict] = []

    seen_inconsistent: set[str] = set()
    for issue in issues:
        if issue.kind == "inconsistent" and issue.original not in seen_inconsistent:
            seen_inconsistent.add(issue.original)
            variants: Counter[str] = Counter()
            for pairs in translations.values():
                t = pairs.get(issue.original, "")
                if t:
                    variants[t] += 1
            inconsistent.append({
                "original": issue.original,
                "variants": dict(variants.most_common()),
            })
        elif issue.kind == "glossary_violation":
            for pairs in translations.values():
                t = pairs.get(issue.original, "")
                if t:
                    glossary_violations.append({
                        "original": issue.original,
                        "translated": t,
                        "term_en": issue.detail.split('"')[1],
                        "term_zh": issue.detail.split('"')[3],
                    })
                    break
        elif issue.kind == "keep_original_violation":
            for pairs in translations.values():
                t = pairs.get(issue.original, "")
                if t:
                    keep_original_violations.append({
                        "original": issue.original,
                        "translated": t,
                        "word": issue.detail.split('"')[1],
                    })
                    break

    return inconsistent, glossary_violations, keep_original_violations


def run(args) -> None:
    """CLI 入口"""
    from .utils import load_json, save_json

    translations: TranslationDict = load_json(args.input)
    glossary_path = getattr(args, "glossary", "config/glossary.yaml")

    issues = check_consistency(translations, glossary_path)

    if not issues:
        log.info("一致性检查通过，未发现问题")
        return

    # 按类型分组输出
    by_kind: dict[str, list[Issue]] = {}
    for issue in issues:
        by_kind.setdefault(issue.kind, []).append(issue)

    kind_labels = {
        "inconsistent": "跨文件不一致",
        "glossary_violation": "术语表违反",
        "keep_original_violation": "专有名词可能被翻译",
    }
    for kind, kind_issues in by_kind.items():
        label = kind_labels.get(kind, kind)
        log.info("=== %s (%d 条) ===", label, len(kind_issues))
        for issue in kind_issues[:20]:  # 每类最多显示 20 条
            log.info("  %s", issue.detail)
        if len(kind_issues) > 20:
            log.info("  ... 还有 %d 条", len(kind_issues) - 20)

    log.info("共发现 %d 个问题", len(issues))

    if getattr(args, "fix", False):
        translations, fix_log = fix_consistency(translations, glossary_path)
        for msg in fix_log:
            log.info("修复: %s", msg)
        save_json(translations, args.input)
        log.info("已修复并保存: %s", args.input)
