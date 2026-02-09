"""JSON <-> Excel 双向转换"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from .utils import TranslationDict, load_json, save_json

log = logging.getLogger(__name__)


def json_to_excel(json_path: str, excel_path: str) -> None:
    """JSON 翻译文件转 Excel"""
    try:
        import pandas as pd
    except ImportError:
        raise SystemExit(
            "需要安装 excel 依赖: pip install 'zedl10n[excel]'"
        )

    if not Path(json_path).exists():
        raise SystemExit(f"文件不存在: {json_path}")

    data: TranslationDict = load_json(json_path)
    rows: list[dict[str, str]] = []

    for file_path, items in data.items():
        for original, translation in items.items():
            rows.append(
                {
                    "文件路径 (勿改)": file_path,
                    "原文": original,
                    "译文": translation,
                    "状态": "已翻译" if translation else "待翻译",
                }
            )

    df = pd.DataFrame(rows)
    df.to_excel(excel_path, index=False, engine="openpyxl")
    log.info("转换成功: %s → %s（%d 条）", json_path, excel_path, len(df))


def excel_to_json(excel_path: str, json_path: str) -> None:
    """Excel 翻译回填到 JSON"""
    try:
        import pandas as pd
    except ImportError:
        raise SystemExit(
            "需要安装 excel 依赖: pip install 'zedl10n[excel]'"
        )

    if not Path(excel_path).exists():
        raise SystemExit(f"文件不存在: {excel_path}")

    df = pd.read_excel(excel_path, engine="openpyxl", dtype=str)
    df.fillna("", inplace=True)

    json_data: TranslationDict = {}
    count = 0

    for _, row in df.iterrows():
        file_path = row.get("文件路径 (勿改)")
        original = row.get("原文")
        translation = row.get("译文")

        if not file_path or not original:
            continue

        if file_path not in json_data:
            json_data[file_path] = {}

        json_data[file_path][str(original)] = str(translation)
        count += 1

    save_json(json_data, json_path)
    log.info("转换成功: %s → %s（%d 条）", excel_path, json_path, count)


def run(args: argparse.Namespace) -> None:
    """CLI 入口"""
    if not args.convert_action:
        raise SystemExit(
            "请指定转换方向: zedl10n convert to_excel 或 to_json"
        )

    json_path = args.json
    excel_path = args.excel

    if args.convert_action == "to_excel":
        json_to_excel(json_path, excel_path)
    elif args.convert_action == "to_json":
        excel_to_json(excel_path, json_path)
