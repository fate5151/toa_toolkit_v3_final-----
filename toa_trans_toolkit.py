#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
ToA (Tales of Androgyny) strings.properties 提取/回注工具 v3 (最终版)
====================================================================
用法：
  python toa_trans_toolkit.py extract-strings   strings.properties --fmt ainiee
  python toa_trans_toolkit.py extract-strings   strings.properties --fmt galtransl
  python toa_trans_toolkit.py inject-strings    strings.properties translated.json output.properties
  python toa_trans_toolkit.py inject-strings    strings.properties translated.json output.properties --wrap 28
  python toa_trans_toolkit.py inject-strings    strings.properties translated.json output.properties --dry-run
  python toa_trans_toolkit.py inject-strings    strings.properties translated.json output.properties --verbose

AiNiee：选「ParaTranz导出」模式导入，译文填入 "translation" 字段
GalTransl：将输出放入 gt_input/ 目录，译文填入 "translation" 字段

回注时自动为长译文添加换行符（\n），避免游戏中文本一行显示不全
  - 占位符保护：{0}、{nom0} 等绝不被断开
  - 英文单词保护：不会在英文单词中间断行
  - 多层转义处理：\\n → \n → 实际换行
"""

import json
import re
import os
import argparse
from pathlib import Path

# 引入共享换行模块
from textwrap_utils import (
    DEFAULT_WRAP_WIDTH,
    normalize_newlines,
    wrap_text,
    process_translation,
)


# ──────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────

def unescape_prop(value: str) -> str:
    r"""还原 .properties 转义：\n → 换行，\! \: \= \\ → 对应字符"""
    value = value.replace(r"\n", "\n")
    value = re.sub(r"\\(.)", lambda m: m.group(1), value)
    return value


def escape_prop(value: str) -> str:
    r"""回注时重新转义 .properties 特殊字符"""
    value = value.replace("\\", "\\\\")
    value = value.replace("\n", r"\n")
    value = value.replace("!", r"\!")
    value = value.replace(":", r"\:")
    return value


def should_skip(key: str, value: str) -> bool:
    """判断是否跳过（不需要翻译）"""
    s = value.strip()
    if not s:
        return True
    if s in {"?", "N/A", "...", "OK"}:
        return True
    if re.fullmatch(r"[\{\}0-9, ]+", s):
        return True
    return False


def extract_fills(text: str) -> list:
    return re.findall(r"\{[^}]+\}", text)


# ──────────────────────────────────────────────
# 解析 strings.properties
# ──────────────────────────────────────────────

def parse_properties(path: str) -> list:
    entries = []
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    continued = False
    current_key = ""
    current_raw = ""

    for line in lines:
        stripped = line.rstrip("\n")

        if continued:
            current_raw += stripped.rstrip("\\")
            if stripped.endswith("\\"):
                continue
            else:
                continued = False
        else:
            if not stripped or stripped.startswith("#") or stripped.startswith("!"):
                continue
            m = re.match(r"^([^=:]+?)\s*[=:]\s*(.*)", stripped)
            if not m:
                continue
            current_key = m.group(1).strip()
            current_raw = m.group(2)
            if current_raw.endswith("\\"):
                current_raw = current_raw[:-1]
                continued = True
                continue

        value = unescape_prop(current_raw)
        entries.append({
            "key":   current_key,
            "value": value,
            "fills": extract_fills(value),
        })

    return entries


# ──────────────────────────────────────────────
# 构建输出格式
# ──────────────────────────────────────────────

def build_ainiee(entries: list) -> list:
    """AiNiee ParaTranz 格式"""
    result = []
    for e in entries:
        if should_skip(e["key"], e["value"]):
            continue
        item = {
            "key":         e["key"],
            "original":    e["value"],
            "translation": "",
            "stage":       0,
        }
        if e["fills"]:
            item["context"] = "占位符保持不变: " + " ".join(e["fills"])
        result.append(item)
    return result


def build_galtransl(entries: list) -> list:
    """GalTransl 格式"""
    result = []
    for e in entries:
        if should_skip(e["key"], e["value"]):
            continue
        item = {
            "name":        e["key"],
            "original":    e["value"],
            "translation": "",
        }
        if e["fills"]:
            item["note"] = "占位符保持不变: " + " ".join(e["fills"])
        result.append(item)
    return result


# ──────────────────────────────────────────────
# 回注
# ──────────────────────────────────────────────

def inject_strings(src_path: str, translated_json: str, out_path: str,
                   wrap_width: int = DEFAULT_WRAP_WIDTH, no_wrap: bool = False,
                   dry_run: bool = False, verbose: bool = False):
    with open(translated_json, "r", encoding="utf-8") as f:
        trans_list = json.load(f)

    # 兼容 AiNiee (key) 和 GalTransl (name) 两种格式
    trans_map = {}
    for item in trans_list:
        key = item.get("key") or item.get("name", "")
        val = item.get("translation", "").strip()
        if key and val:
            trans_map[key] = val

    with open(src_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    out_lines = []
    wrap_count = 0
    norm_count = 0
    wrap_details = []

    for line in lines:
        stripped = line.rstrip("\n")
        m = re.match(r"^([^=:]+?)\s*[=:]\s*(.*)", stripped)
        if m:
            key = m.group(1).strip()
            if key in trans_map:
                # ── 换行处理 ──
                processed, was_wrapped = process_translation(
                    trans_map[key], width=wrap_width, no_wrap=no_wrap
                )

                # 检测是否仅做了换行符标准化
                norm_only = (not was_wrapped) and (processed != trans_map[key])
                if was_wrapped:
                    wrap_count += 1
                elif norm_only:
                    norm_count += 1

                # verbose: 记录换行详情
                if verbose and (was_wrapped or norm_only):
                    wrap_details.append({
                        "key": key,
                        "before": trans_map[key],
                        "after": processed,
                        "type": "自动换行" if was_wrapped else "换行符标准化",
                    })

                # 转义为 .properties 格式（实际换行 → \n 字面量）
                out_lines.append(f"{key}={escape_prop(processed)}\n")
                continue
        out_lines.append(line)

    # ── 输出 ──
    if dry_run:
        print(f"\n🔍 [DRY-RUN] 预览模式，不写入文件")
    else:
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.writelines(out_lines)

    print(f"\n✅ 回注{'预览' if dry_run else '完成'}：{len(trans_map)} 条")
    if wrap_count:
        print(f"   自动换行:     {wrap_count} 条  (每行≤{wrap_width}字)")
    if norm_count:
        print(f"   换行符标准化: {norm_count} 条  (\\n → 真换行)")
    if not dry_run:
        print(f"   输出: {out_path}")

    # ── verbose: 显示换行详情 ──
    if verbose and wrap_details:
        print(f"\n📋 换行详情 ({len(wrap_details)} 条):")
        print("─" * 60)
        for i, detail in enumerate(wrap_details, 1):
            print(f"  [{i}] {detail['key']}  ({detail['type']})")
            print(f"      前: {detail['before']!r}")
            print(f"      后: {detail['after']!r}")
            for j, line in enumerate(detail['after'].split('\n')):
                print(f"      行{j+1} ({len(line)}字): {line}")
            if i < len(wrap_details):
                print()


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

def cmd_extract(args):
    entries = parse_properties(args.input)
    total   = len(entries)

    if args.fmt == "ainiee":
        result  = build_ainiee(entries)
        default = "strings_ainiee.json"
    else:
        result  = build_galtransl(entries)
        os.makedirs("gt_input", exist_ok=True)
        default = os.path.join("gt_input", "strings_galtransl.json")

    out = args.output or default
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"✅ strings.properties 提取完毕")
    print(f"   总条目: {total}  跳过: {total - len(result)}  待翻译: {len(result)}")
    print(f"   输出: {out}")


def cmd_inject(args):
    inject_strings(args.source, args.translated, args.output,
                   wrap_width=args.wrap, no_wrap=args.no_wrap,
                   dry_run=args.dry_run, verbose=args.verbose)


def main():
    parser = argparse.ArgumentParser(
        description="ToA strings.properties 提取/回注工具 v3 (最终版)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p1 = sub.add_parser("extract-strings")
    p1.add_argument("input")
    p1.add_argument("--fmt", choices=["ainiee", "galtransl"], default="ainiee")
    p1.add_argument("--output", default="")

    p2 = sub.add_parser("inject-strings")
    p2.add_argument("source")
    p2.add_argument("translated")
    p2.add_argument("output")
    p2.add_argument("--wrap", type=int, default=DEFAULT_WRAP_WIDTH,
                    help=f"每行最大字符数，超长译文自动添加换行符（默认 {DEFAULT_WRAP_WIDTH}）")
    p2.add_argument("--no-wrap", action="store_true", default=False,
                    help="禁用自动换行（仅处理字面 \\n 转换）")
    p2.add_argument("--dry-run", action="store_true", default=False,
                    help="预览模式：只显示换行效果，不写入文件")
    p2.add_argument("--verbose", "-v", action="store_true", default=False,
                    help="显示每条换行的详细前后对比")

    args = parser.parse_args()
    {"extract-strings": cmd_extract, "inject-strings": cmd_inject}[args.command](args)


if __name__ == "__main__":
    main()
