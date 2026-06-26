#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ToA 增量翻译工具
=================
解决版本更新后只翻译新增/修改内容的问题。

核心概念：
  翻译缓存（trans_cache.json）：记录所有已翻译的条目
    格式：{ "key": {"en": "原文", "zh": "译文"} }

命令：
  init     首次使用，将已翻译完的文件导入缓存
  diff     版本更新后，对比新旧文件，提取需要重新翻译的条目
  apply    翻译完成后，将新译文合并进缓存并生成回注文件
  export   从缓存直接生成回注文件（无需重新翻译）
  stats    查看缓存统计

用法示例：
  # 首次：将已翻译好的文件导入缓存
  python update_tool.py init --strings   strings_merged.json
  python update_tool.py init --encounters encounters_merged.json

  # 游戏更新后：提取新版本文件，找出差异
  python update_tool.py diff new_strings_ainiee.json     --output strings_todo.json
  python update_tool.py diff new_encounters_paratranz.json --output encounters_todo.json

  # 用 AiNiee 翻译 *_todo.json，翻译完后导入缓存
  python update_tool.py apply strings_todo_translated.json
  python update_tool.py apply encounters_todo_translated.json

  # 生成最终回注文件
  python update_tool.py export --output strings_final.json
  python update_tool.py export --output encounters_final.json
"""

import json
import os
import argparse
from pathlib import Path
from datetime import datetime

CACHE_FILE = "trans_cache.json"


# ──────────────────────────────────────────────
# 缓存读写
# ──────────────────────────────────────────────

def load_cache() -> dict:
    """加载翻译缓存，格式：{key: {en, zh, updated}}"""
    if not os.path.exists(CACHE_FILE):
        return {}
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_cache(cache: dict):
    with open(CACHE_FILE, "w", encoding="utf-8", newline="\n") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    print(f"✅ 缓存已保存：{CACHE_FILE}（{len(cache)} 条）")


# ──────────────────────────────────────────────
# init：将已翻译文件导入缓存
# ──────────────────────────────────────────────

def cmd_init(args):
    """首次使用，支持同时传入【提取的原文文件】和【翻译后的译文文件】"""
    cache = load_cache()
    before = len(cache)
    
    orig_map = {}
    trans_map = {}
    
    # 自动识别并分离原文和译文
    for path in args.files:
        print(f"读取: {path}")
        data = json.load(open(path, encoding="utf-8"))
        for item in data:
            key = item.get("key", "")
            if not key: continue
            en = item.get("original", "")
            zh = item.get("translation", "")
            if en: orig_map[key] = en
            if zh: trans_map[key] = zh
            
    imported = 0
    all_keys = set(orig_map.keys()) | set(trans_map.keys())
    for key in all_keys:
        zh = trans_map.get(key, "")
        en = orig_map.get(key, "")
        if zh.strip():
            cache[key] = {
                "en":      en,
                "zh":      zh,
                "updated": datetime.now().strftime("%Y-%m-%d"),
            }
            imported += 1
            
    save_cache(cache)
    print(f"  新增/更新: {len(cache) - before} 条  |  缓存总计: {len(cache)} 条")


# ──────────────────────────────────────────────
# diff：对比新版本，找出需要翻译的条目
# ──────────────────────────────────────────────

def cmd_diff(args):
    """
    对比新提取的文件与缓存：
    - 原文未变 且 缓存有译文 → 直接跳过
    - 新增 key → 输出（需翻译）
    - 原文已修改 → 输出（需重译）
    """
    cache = load_cache()
    print(f"缓存条目: {len(cache)}")

    new_data = json.load(open(args.input, encoding="utf-8"))
    print(f"新版本条目: {len(new_data)}")

    need_translate = []   # 需要翻译的
    reused         = []   # 直接复用
    changed        = []   # 原文变更

    for item in new_data:
        key = item.get("key", "")
        en  = item.get("original", "").strip()

        if not key or not en:
            continue

        if key in cache:
            cached = cache[key]
            if cached["en"].strip() == en:
                # 原文未变，直接复用
                reused.append(key)
            else:
                # 原文已修改，需重译
                changed.append(key)
                need_translate.append({
                    "key":         key,
                    "original":    en,
                    "translation": "",
                    "stage":       0,
                    "context":     item.get("context", "") + " [原文已修改]",
                })
        else:
            # 新增 key
            need_translate.append({
                "key":         key,
                "original":    en,
                "translation": "",
                "stage":       0,
                "context":     item.get("context", "") + " [新增]",
            })

    # 输出
    out_path = args.output
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(need_translate, f, ensure_ascii=False, indent=2)

    # 同时生成一份可直接回注的完整文件（已翻译 + 待翻译占位）
    # 这样即使新条目还没翻译，已有译文也能正常回注
    full_out = out_path.replace(".json", "_full.json")
    full = []
    for item in new_data:
        key = item.get("key", "")
        en  = item.get("original", "").strip()
        if key in cache and cache[key]["en"].strip() == en:
            full.append({
                "key":         key,
                "original":    en,
                "translation": cache[key]["zh"],
                "stage":       1,
            })
        else:
            full.append({
                "key":         key,
                "original":    en,
                "translation": "",
                "stage":       0,
            })
    with open(full_out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(full, f, ensure_ascii=False, indent=2)

    print(f"\n📊 差异分析结果")
    print(f"   直接复用（原文未变）: {len(reused):>5} 条")
    print(f"   原文已修改（需重译）: {len(changed):>5} 条")
    print(f"   新增（需翻译）:       {len(new_data)-len(reused)-len(changed):>5} 条")
    print(f"   ─────────────────────────────")
    print(f"   本次需翻译总计:       {len(need_translate):>5} 条")
    print(f"\n   待翻译文件: {out_path}")
    print(f"   完整文件:   {full_out}  ← 可立即用于回注（含所有已有译文）")

    if len(need_translate) == 0:
        print(f"\n🎉 无需翻译！新版本全部内容已在缓存中。")
    else:
        print(f"\n➡️  下一步：用 AiNiee 翻译 {out_path}")
        print(f"   翻译完后运行: python update_tool.py apply {out_path}")


# ──────────────────────────────────────────────
# apply：将新译文合并进缓存
# ──────────────────────────────────────────────

def cmd_apply(args):
    """翻译完成后，将新译文合并进缓存"""
    cache = load_cache()
    before = len(cache)

    for path in args.files:
        print(f"导入译文: {path}")
        data = json.load(open(path, encoding="utf-8"))
        imported = 0
        skipped  = 0
        for item in data:
            key  = item.get("key", "")
            en   = item.get("original", "").strip()
            zh   = item.get("translation", "").strip()
            if key and zh:
                cache[key] = {
                    "en":      en,
                    "zh":      zh,
                    "updated": datetime.now().strftime("%Y-%m-%d"),
                }
                imported += 1
            else:
                skipped += 1
        print(f"  导入: {imported} 条  |  跳过(空译文): {skipped} 条")

    save_cache(cache)
    print(f"  缓存新增: {len(cache) - before} 条  |  缓存总计: {len(cache)} 条")


# ──────────────────────────────────────────────
# export：从缓存生成回注文件
# ──────────────────────────────────────────────

def cmd_export(args):
    """从缓存生成可直接用于 inject 的完整回注文件"""
    cache = load_cache()
    if not cache:
        print("❌ 缓存为空，请先运行 init 或 apply")
        return

    result = [
        {
            "key":         k,
            "original":    v["en"],
            "translation": v["zh"],
            "stage":       1,
        }
        for k, v in cache.items()
        if v.get("zh", "").strip()
    ]

    with open(args.output, "w", encoding="utf-8", newline="\n") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"✅ 导出完成：{args.output}（{len(result)} 条）")
    print(f"   直接用于 inject-strings 或 inject encounters")


# ──────────────────────────────────────────────
# stats：统计
# ──────────────────────────────────────────────

def cmd_stats(args):
    cache = load_cache()
    if not cache:
        print("缓存为空")
        return

    strings_keys    = [k for k in cache if "." in k and "[" not in k]
    encounter_keys  = [k for k in cache if "[" in k]
    total_zh        = sum(1 for v in cache.values() if v.get("zh","").strip())

    print(f"📊 翻译缓存统计")
    print(f"   总条目:            {len(cache)}")
    print(f"   strings 条目:      {len(strings_keys)}")
    print(f"   encounters 条目:   {len(encounter_keys)}")
    print(f"   有译文:            {total_zh}")
    print(f"   缺译文:            {len(cache) - total_zh}")

    # 最近更新
    dates = sorted(set(v.get("updated","") for v in cache.values() if v.get("updated")))
    if dates:
        print(f"   最早更新:          {dates[0]}")
        print(f"   最近更新:          {dates[-1]}")


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="ToA 增量翻译工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # init
    p1 = sub.add_parser("init", help="将已翻译文件导入缓存（首次使用）")
    p1.add_argument("files", nargs="+", help="已翻译的 merged JSON 文件")

    # diff
    p2 = sub.add_parser("diff", help="对比新版本，找出需要翻译的条目")
    p2.add_argument("input",    help="新版本提取的 JSON 文件")
    p2.add_argument("--output", "-o", default="todo.json", help="输出待翻译文件")

    # apply
    p3 = sub.add_parser("apply", help="将新译文合并进缓存")
    p3.add_argument("files", nargs="+", help="AiNiee 翻译完成的 JSON 文件")

    # export
    p4 = sub.add_parser("export", help="从缓存生成回注文件")
    p4.add_argument("--output", "-o", default="final_for_inject.json")

    # stats
    sub.add_parser("stats", help="查看缓存统计")

    args = parser.parse_args()
    {
        "init":   cmd_init,
        "diff":   cmd_diff,
        "apply":  cmd_apply,
        "export": cmd_export,
        "stats":  cmd_stats,
    }[args.command](args)


if __name__ == "__main__":
    main()
