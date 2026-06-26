#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
ToA (Tales of Androgyny) strings.properties 提取/回注工具 v4
====================================================================
v4 更新内容（相对 v3）：
  - 默认换行宽度调整为 32 字（按对话框实测宽度估算）
  - 新增"合并重排"（reflow）：先合并已有换行再统一重新断行，
    解决"断行长短不一、留白过多"的问题（默认开启）
  - 新增最大行数控制：对话框最多显示 5 行，超出部分游戏里看不到；
    排版时会在 [wrap, max-width] 区间内尝试放宽行宽以压缩行数
  - 排版后仍超过最大行数的条目会生成 overflow 报告（.overflow.txt），
    需要人工精简译文
  - --no-reflow 可关闭合并重排，恢复 v3 行为（仅对超长行追加断行，
    保留译者/原文已有的换行位置）

用法：
  python toa_trans_toolkit.py extract-strings   strings.properties --fmt ainiee
  python toa_trans_toolkit.py extract-strings   strings.properties --fmt galtransl
  python toa_trans_toolkit.py inject-strings    strings.properties translated.json output.properties
  python toa_trans_toolkit.py inject-strings    strings.properties translated.json output.properties --wrap 32 --max-lines 5
  python toa_trans_toolkit.py inject-strings    strings.properties translated.json output.properties --dry-run --verbose
  python toa_trans_toolkit.py inject-strings    strings.properties translated.json output.properties --no-reflow

AiNiee：选「ParaTranz导出」模式导入，译文填入 "translation" 字段
GalTransl：将输出放入 gt_input/ 目录，译文填入 "translation" 字段

回注时自动为长译文添加换行符（\n），避免游戏中文本一行显示不全
  - 占位符保护：{0}、{nom0} 等绝不被断开
  - 英文单词保护：不会在英文单词中间断行
  - 多层转义处理：\\n → \n → 实际换行
  - 合并重排 + 最大行数控制（见上方 v4 说明）
"""

import json
import re
import os
import argparse
from pathlib import Path

# 引入共享换行模块
from textwrap_utils import (
    DEFAULT_WRAP_WIDTH,
    DEFAULT_MAX_LINES,
    MAX_WIDTH_CAP,
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
                    dry_run: bool = False, verbose: bool = False,
                    max_lines: int = DEFAULT_MAX_LINES, max_width: int = MAX_WIDTH_CAP,
                    reflow: bool = True):
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

    out_lines     = []
    wrap_count    = 0
    overflow_list = []   # (key, 行数)
    wrap_details  = []

    # max_lines 传 0 视为不限制
    effective_max_lines = max_lines if max_lines else None

    for line in lines:
        stripped = line.rstrip("\n")
        m = re.match(r"^([^=:]+?)\s*[=:]\s*(.*)", stripped)
        if m:
            key = m.group(1).strip()
            if key in trans_map:
                # ── 换行处理 ──
                processed, was_changed, exceeds = process_translation(
                    trans_map[key], width=wrap_width, no_wrap=no_wrap,
                    reflow=reflow, max_lines=effective_max_lines, max_width=max_width
                )

                if was_changed:
                    wrap_count += 1

                if exceeds:
                    overflow_list.append((key, processed.count('\n') + 1))

                # verbose: 记录换行详情
                if verbose and was_changed:
                    wrap_details.append({
                        "key": key,
                        "before": trans_map[key],
                        "after": processed,
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
    print(f"   换行/重排:    {wrap_count} 条  "
          f"(起始宽度≤{wrap_width}字，{'已启用' if reflow else '未启用'}合并重排)")
    if not dry_run:
        print(f"   输出: {out_path}")

    # ── 超出最大行数的条目报告 ──
    if effective_max_lines and overflow_list:
        print(f"\n⚠️ 排版后仍超过 {effective_max_lines} 行的条目"
              f"（已尝试放宽至{max_width}字仍超出，需人工精简译文）: {len(overflow_list)} 条")
        for k, n in overflow_list[:20]:
            print(f"   {k}  ({n} 行)")
        if len(overflow_list) > 20:
            print(f"   ...另外 {len(overflow_list) - 20} 条，详见完整报告文件")

        if not dry_run:
            overflow_path = out_path + ".overflow.txt"
            with open(overflow_path, "w", encoding="utf-8") as f:
                for k, n in overflow_list:
                    f.write(f"{k}\t{n}行\n")
            print(f"   完整列表已写入: {overflow_path}")
    elif effective_max_lines:
        print(f"\n✅ 所有条目均未超过 {effective_max_lines} 行限制")

    # ── verbose: 显示换行详情 ──
    if verbose and wrap_details:
        print(f"\n📋 换行详情 ({len(wrap_details)} 条):")
        print("─" * 60)
        for i, detail in enumerate(wrap_details, 1):
            print(f"  [{i}] {detail['key']}")
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
                    dry_run=args.dry_run, verbose=args.verbose,
                    max_lines=args.max_lines, max_width=args.max_width,
                    reflow=args.reflow)


def main():
    parser = argparse.ArgumentParser(
        description="ToA strings.properties 提取/回注工具 v4",
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
                     help=f"起始换行宽度，超长译文自动添加换行符（默认 {DEFAULT_WRAP_WIDTH}）")
    p2.add_argument("--no-wrap", action="store_true", default=False,
                     help="禁用自动换行（仅处理字面 \\n 转换）")
    p2.add_argument("--max-lines", type=int, default=DEFAULT_MAX_LINES,
                     help=f"最多显示行数，超出部分游戏里看不到"
                          f"（默认 {DEFAULT_MAX_LINES}，传 0 表示不限制）")
    p2.add_argument("--max-width", type=int, default=MAX_WIDTH_CAP,
                     help=f"放宽换行宽度的硬上限（默认 {MAX_WIDTH_CAP}）")
    p2.add_argument("--no-reflow", dest="reflow", action="store_false", default=True,
                     help="禁用合并重排，恢复为仅对超长行追加换行")
    p2.add_argument("--dry-run", action="store_true", default=False,
                     help="预览模式：只显示换行效果，不写入文件")
    p2.add_argument("--verbose", "-v", action="store_true", default=False,
                     help="显示每条换行的详细前后对比")

    args = parser.parse_args()
    {"extract-strings": cmd_extract, "inject-strings": cmd_inject}[args.command](args)


if __name__ == "__main__":
    main()
