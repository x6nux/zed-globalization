"""统一 CLI 入口"""

from __future__ import annotations

import argparse
import sys


def _add_ai_args(parser: argparse.ArgumentParser) -> None:
    """为需要 AI 的子命令添加公共参数"""
    parser.add_argument("--base-url", default="", help="AI API 地址")
    parser.add_argument("--api-key", default="", help="AI API 密钥")
    parser.add_argument("--model", default="", help="AI 模型名称")
    parser.add_argument(
        "--concurrency", type=int, default=0, help="AI 并发数（默认 5）"
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="zedl10n",
        description="Zed 编辑器多语言本地化工具链",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="显示调试日志"
    )
    sub = parser.add_subparsers(dest="command", help="可用子命令")

    # --- scan ---
    p_scan = sub.add_parser("scan", help="AI 扫描识别需翻译的 .rs 文件")
    p_scan.add_argument(
        "--source-root", required=True, help="Zed 源码根目录"
    )
    p_scan.add_argument(
        "--prev-result", default="",
        help="上次扫描结果 scan_result.json 路径（提供则启用增量模式）",
    )
    p_scan.add_argument(
        "--changed", default="",
        help="变化文件列表（每行一个相对路径的文本文件）",
    )
    p_scan.add_argument(
        "--deleted", default="",
        help="删除文件列表（每行一个相对路径的文本文件）",
    )
    p_scan.add_argument(
        "--version", default="",
        help="当前扫描对应的 Zed 版本号（保存到 scan_result.json）",
    )
    p_scan.add_argument(
        "--output", default="scan_result.json",
        help="扫描结果输出路径（默认 scan_result.json）",
    )
    _add_ai_args(p_scan)

    # --- extract ---
    p_ext = sub.add_parser("extract", help="提取字符串 + 上下文")
    p_ext.add_argument(
        "--source-root", required=True, help="Zed 源码根目录"
    )
    p_ext.add_argument(
        "--output", default="string.json", help="输出文件路径"
    )
    p_ext.add_argument(
        "--files", nargs="*", help="指定文件列表（省略则使用 scan 结果）"
    )

    # --- translate ---
    p_tr = sub.add_parser("translate", help="AI 并发翻译")
    p_tr.add_argument(
        "--input", required=True, help="string.json 路径"
    )
    p_tr.add_argument(
        "--output", required=True, help="翻译输出路径（如 i18n/zh.json）"
    )
    p_tr.add_argument(
        "--context", default="", help="string_context.json 路径"
    )
    p_tr.add_argument(
        "--glossary", default="config/glossary.yaml", help="术语表路径"
    )
    p_tr.add_argument(
        "--mode",
        choices=["incremental", "full"],
        default="incremental",
        help="翻译模式",
    )
    p_tr.add_argument(
        "--lang", default="zh-CN", help="目标语言"
    )
    p_tr.add_argument(
        "--source-root", default="", help="Zed 源码根目录（用于传递完整源文件上下文）"
    )
    _add_ai_args(p_tr)

    # --- replace ---
    p_rep = sub.add_parser("replace", help="替换 Zed 源码中的字符串")
    p_rep.add_argument(
        "--input", required=True, help="翻译 JSON 文件路径"
    )
    p_rep.add_argument(
        "--source-root", default=".", help="Zed 源码根目录"
    )
    p_rep.add_argument(
        "--do-not-translate", default="",
        help="禁止翻译列表 JSON 文件路径",
    )

    # --- convert ---
    p_conv = sub.add_parser("convert", help="JSON <-> Excel 转换")
    p_conv_sub = p_conv.add_subparsers(dest="convert_action")

    p_to_excel = p_conv_sub.add_parser("to_excel", help="JSON 转 Excel")
    p_to_excel.add_argument("--json", required=True, help="JSON 文件路径")
    p_to_excel.add_argument(
        "--excel", default="translation_work.xlsx", help="Excel 输出路径"
    )

    p_to_json = p_conv_sub.add_parser("to_json", help="Excel 转 JSON")
    p_to_json.add_argument("--json", required=True, help="JSON 文件路径")
    p_to_json.add_argument(
        "--excel", required=True, help="Excel 文件路径"
    )

    # --- pipeline ---
    p_pipe = sub.add_parser("pipeline", help="一键流水线: 提取→翻译")
    p_pipe.add_argument(
        "--source-root", required=True, help="Zed 源码根目录"
    )
    p_pipe.add_argument(
        "--lang", default="zh-CN", help="目标语言"
    )
    p_pipe.add_argument(
        "--mode",
        choices=["incremental", "full"],
        default="full",
        help="翻译模式",
    )
    p_pipe.add_argument(
        "--glossary", default="config/glossary.yaml", help="术语表路径"
    )
    _add_ai_args(p_pipe)

    # --- release-notes ---
    p_rn = sub.add_parser(
        "release-notes", help="获取并翻译 Zed Release Notes",
    )
    p_rn.add_argument(
        "--version", required=True, help="Zed 版本号（如 v0.222.4）",
    )
    p_rn.add_argument(
        "--lang", default="zh-CN", help="目标语言",
    )
    p_rn.add_argument(
        "--output", default="/tmp/release_body.md",
        help="输出文件路径",
    )
    _add_ai_args(p_rn)

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    from .utils import setup_logging

    setup_logging(args.verbose)

    if args.command == "scan":
        _run_scan(args)
    elif args.command == "extract":
        from .extract import run

        run(args)
    elif args.command == "translate":
        from .translate import run

        run(args)
    elif args.command == "replace":
        from .replace import run

        run(args)
    elif args.command == "convert":
        from .convert import run

        run(args)
    elif args.command == "pipeline":
        _run_pipeline(args)
    elif args.command == "release-notes":
        from .release_notes import run

        run(args)


def _read_lines(path: str) -> list[str]:
    """读取文本文件，返回非空行列表"""
    from pathlib import Path

    p = Path(path)
    if not p.exists():
        return []
    return [line.strip() for line in p.read_text().splitlines() if line.strip()]


def _run_scan(args: argparse.Namespace) -> None:
    """scan 命令入口：支持全量 / 增量两种模式"""
    import logging

    from .scan import (
        load_scan_result,
        save_scan_result,
        scan_files,
        scan_incremental,
    )
    from .utils import AIConfig

    log = logging.getLogger(__name__)
    ai_cfg = AIConfig(
        base_url=args.base_url,
        api_key=args.api_key,
        model=args.model,
        concurrency=args.concurrency,
    )

    prev_result_path = getattr(args, "prev_result", "")
    prev = load_scan_result(prev_result_path) if prev_result_path else None

    if prev and prev.get("files"):
        # 增量模式
        changed = _read_lines(args.changed) if args.changed else []
        deleted = _read_lines(args.deleted) if args.deleted else []
        if not changed and not deleted:
            log.warning("增量模式但未提供变化/删除文件列表，回退到全量扫描")
            files = scan_files(args.source_root, ai_cfg)
        else:
            files = scan_incremental(
                args.source_root, ai_cfg, changed, deleted, prev["files"],
            )
    else:
        # 全量模式
        files = scan_files(args.source_root, ai_cfg)
        # 全量模式返回绝对路径，转为相对路径
        from pathlib import Path

        root = Path(args.source_root)
        files = [
            str(Path(f).relative_to(root)) if Path(f).is_absolute() else f
            for f in files
        ]

    version = getattr(args, "version", "") or "unknown"
    save_scan_result(args.output, version, files)
    log.info("扫描完成，共 %d 个文件需要翻译", len(files))


def _run_pipeline(args: argparse.Namespace) -> None:
    """一键流水线: 提取 → 翻译（跳过 AI 扫描，直接使用所有 .rs 文件）"""
    import logging
    import time
    from pathlib import Path

    from .utils import AIConfig

    log = logging.getLogger(__name__)
    t0 = time.time()

    ai_cfg = AIConfig(
        base_url=args.base_url,
        api_key=args.api_key,
        model=args.model,
        concurrency=args.concurrency,
    )
    ai_cfg.validate()

    # 1. 提取
    log.info("=" * 50)
    log.info("阶段 1/2: 字符串提取")
    log.info("=" * 50)
    t1 = time.time()
    from .extract import extract_all
    from .scan import find_all_rs_files

    all_files = find_all_rs_files(args.source_root)
    abs_files = [str(f) for f in all_files]

    if not abs_files:
        log.warning("未发现 .rs 文件，流水线结束")
        return

    strings_path = "string.json"
    context_path = "string_context.json"
    all_strings = extract_all(abs_files, strings_path, context_path)
    total_strings = sum(len(v) for v in all_strings.values())
    log.info("提取完成: %d 个字符串 (耗时 %.0fs)", total_strings, time.time() - t1)

    # 2. 翻译
    log.info("=" * 50)
    log.info("阶段 2/2: AI 翻译")
    log.info("=" * 50)
    t2 = time.time()
    from .translate import translate_all

    output_path = f"i18n/{args.lang}.json"
    translate_all(
        strings_path=strings_path,
        output_path=output_path,
        context_path=context_path,
        glossary_path=args.glossary,
        mode=args.mode,
        lang=args.lang,
        ai_cfg=ai_cfg,
        source_root=args.source_root,
    )
    log.info("翻译完成 (耗时 %.0fs)", time.time() - t2)

    log.info("=" * 50)
    log.info("全部完成! 总耗时 %.0fs, 输出: %s", time.time() - t0, output_path)
    log.info("=" * 50)
