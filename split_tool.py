#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AiNiee 大文件分批/合并工具 v2
==============================
split  去重 + 分批，生成干净的 AiNiee 导入文件（不含内部字段）
merge  翻译完成后合并还原（自动读取去重映射表）

用法：
  python split_tool.py split  encounters_paratranz.json --size 3000 --no-context
  python split_tool.py merge  encounters_paratranz_parts/
"""

import json
import os
import argparse
from pathlib import Path
from collections import defaultdict

DEDUP_MAP_FILE = "dedup_map.json"   # 存放 orig → [key, key, ...] 映射


def load_json(path: str) -> list:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data, path: str):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ──────────────────────────────────────────────
# split
# ──────────────────────────────────────────────

def cmd_split(args):
    print(f"读取: {args.input}")
    data = load_json(args.input)
    total_orig = len(data)

    out_dir = args.output_dir or (Path(args.input).stem + "_parts")
    os.makedirs(out_dir, exist_ok=True)

    if args.dedup:
        # orig_text → [key1, key2, ...]（用于 merge 还原）
        orig_to_keys: dict[str, list] = defaultdict(list)
        for item in data:
            orig_to_keys[item["original"]].append(item["key"])

        # 去重：每个唯一原文只保留一条
        seen = set()
        deduped = []
        for item in data:
            orig = item["original"]
            if orig not in seen:
                seen.add(orig)
                entry = {
                    "key":         item["key"],   # 代表该原文的第一个 key
                    "original":    orig,
                    "translation": "",
                    "stage":       0,
                }
                # context 可选保留
                if not args.no_context and "context" in item:
                    entry["context"] = item["context"]
                deduped.append(entry)

        saved = total_orig - len(deduped)
        print(f"去重：{total_orig} → {len(deduped)} 条（节省 {saved} 条，{saved*100//total_orig}%）")

        # 单独保存去重映射表（不混入 AiNiee 文件）
        dedup_map_path = os.path.join(out_dir, DEDUP_MAP_FILE)
        save_json(dict(orig_to_keys), dedup_map_path)
        print(f"去重映射表: {dedup_map_path}")

        batches_data = deduped

    else:
        if args.no_context:
            for item in data:
                item.pop("context", None)
        batches_data = data

    # 分批，输出文件只含 AiNiee 需要的字段
    size = args.size
    batches = [batches_data[i:i+size] for i in range(0, len(batches_data), size)]

    for i, batch in enumerate(batches, 1):
        # 确保输出文件只有干净的4个字段
        clean_batch = []
        for item in batch:
            entry = {
                "key":         item["key"],
                "original":    item["original"],
                "translation": item.get("translation", ""),
                "stage":       item.get("stage", 0),
            }
            if not args.no_context and "context" in item:
                entry["context"] = item["context"]
            clean_batch.append(entry)

        path = os.path.join(out_dir, f"part_{i:03d}.json")
        save_json(clean_batch, path)
        size_kb = os.path.getsize(path) // 1024
        print(f"  part_{i:03d}.json  {len(clean_batch):>5} 条  {size_kb} KB")

    print(f"\n✅ 共分 {len(batches)} 批，输出目录: {out_dir}/")
    print(f"   AiNiee：逐个载入 part_*.json，选「ParaTranz导出」模式翻译并导出")
    print(f"   翻译完后运行: python split_tool.py merge {out_dir}/")


# ──────────────────────────────────────────────
# merge
# ──────────────────────────────────────────────

def cmd_merge(args):
    in_dir = args.input_dir.rstrip("/\\")
    files  = sorted(Path(in_dir).glob("part_*.json"))

    if not files:
        print(f"❌ 在 {in_dir}/ 中找不到 part_*.json 文件")
        return

    print(f"找到 {len(files)} 个文件，合并中...")

    # 收集所有译文：key → translation
    key_to_trans:  dict[str, str] = {}
    orig_to_trans: dict[str, str] = {}
    total_translated = 0
    total_empty      = 0

    for fpath in files:
        batch = load_json(str(fpath))
        for item in batch:
            trans = item.get("translation", "").strip()
            if not trans:
                total_empty += 1
                continue
            total_translated += 1
            key_to_trans[item["key"]]      = trans
            orig_to_trans[item["original"]] = trans

    print(f"  有效译文: {total_translated} 条  |  未翻译(空): {total_empty} 条")

    # 加载去重映射表（如果有），展开同文本的所有 key
    dedup_map_path = os.path.join(in_dir, DEDUP_MAP_FILE)
    expanded = dict(key_to_trans)  # 先复制已有的 key→trans

    if os.path.exists(dedup_map_path):
        dedup_map: dict[str, list] = load_json(dedup_map_path)
        extra = 0
        for orig, keys in dedup_map.items():
            if orig in orig_to_trans:
                for k in keys:
                    if k not in expanded:
                        expanded[k] = orig_to_trans[orig]
                        extra += 1
        print(f"  去重展开: 额外补充 {extra} 条 key")
    else:
        print(f"  ⚠ 未找到去重映射表，仅合并已有 key")

    print(f"  最终覆盖 key: {len(expanded)} 条")

    # 输出标准 ParaTranz 格式（用于 inject 回注）
    result = [
        {
            "key":         k,
            "original":    "",
            "translation": v,
            "stage":       1,
        }
        for k, v in expanded.items()
    ]

    save_json(result, args.output)
    print(f"\n✅ 合并完成 → {args.output}（可直接用于 inject 回注）")


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="AiNiee 大文件分批/合并工具 v2",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p1 = sub.add_parser("split", help="去重 + 分批")
    p1.add_argument("input")
    p1.add_argument("--size",       type=int, default=5000)
    p1.add_argument("--no-dedup",   dest="dedup", action="store_false", default=True)
    p1.add_argument("--no-context", action="store_true", default=False)
    p1.add_argument("--output-dir", default="")

    p2 = sub.add_parser("merge", help="翻译完成后合并还原")
    p2.add_argument("input_dir")
    p2.add_argument("--output", default="merged_for_inject.json")

    args = parser.parse_args()
    {"split": cmd_split, "merge": cmd_merge}[args.command](args)


if __name__ == "__main__":
    main()
