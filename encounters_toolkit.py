#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ToA encounters.json 提取 / 回注工具 v4
================================================
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

v3 内容（保留）：
  - 过滤 <CHARACTER_TAG> 格式的 speaker（游戏内部标签，不需要翻译）
  - 过滤纯符号/点号/空白文本
  - 过滤故障乱码文本
  - 输出文件不含内部字段（_all_keys 等）
  - 进度显示
  - 占位符保护：{0}、{nom0} 等绝不被断开
  - 英文单词保护：不会在英文单词中间断行
  - 多层转义处理：\\n → \n → 实际换行
  - --dry-run 预览模式
  - --verbose 显示换行详情

用法：
  python encounters_toolkit.py extract encounters.json [--output 输出.json]
  python encounters_toolkit.py inject  encounters.json 译好的.json [--output 输出.json]
  python encounters_toolkit.py inject  encounters.json 译好的.json --wrap 32 --max-lines 5
  python encounters_toolkit.py inject  encounters.json 译好的.json --dry-run --verbose
  python encounters_toolkit.py inject  encounters.json 译好的.json --no-reflow   # 恢复 v3 行为
"""

import json
import re
import os
import sys
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
# 过滤规则
# ──────────────────────────────────────────────

# 纯点号 / 纯空白 / 空字符串
RE_DOTS_OR_BLANK = re.compile(r'^[\s.。…]*$')

# 故障乱码文本（超长重复特殊符号）
RE_GLITCH = re.compile(r'[#!W]{20,}')

# 游戏内部角色标签，如 <DARK_KNIGHT> <GOBLIN> 等，不是真实说话人名称
RE_GAME_TAG = re.compile(r'^<[A-Z_]+>$')


def should_skip_text(text: str) -> bool:
    """返回 True 表示跳过"""
    if not text or not text.strip():
        return True
    if RE_DOTS_OR_BLANK.match(text):
        return True
    if RE_GLITCH.search(text):
        return True
    if text.strip() in {".", "...", "....", ".................", "ERROR"}:
        return True
    return False


def should_skip_speaker(speaker: str) -> bool:
    """返回 True 表示 speaker 不提取"""
    if not speaker or not speaker.strip():
        return True
    # Hiro 是玩家名占位符，游戏运行时自动替换
    if speaker.strip() == "Hiro":
        return True
    # <DARK_KNIGHT> <GOBLIN> 等游戏内部标签，游戏自动替换为角色名，不翻译
    if RE_GAME_TAG.match(speaker.strip()):
        return True
    return False


# ──────────────────────────────────────────────
# 提取
# ──────────────────────────────────────────────

def extract(src_path: str, out_path: str):
    print(f"读取: {src_path}")
    with open(src_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    result = []
    stats = {
        "encounters":    0,
        "total_items":   0,
        "extracted":     0,
        "skipped_blank": 0,
        "skipped_tag":   0,
    }

    enc_list = list(data.items())
    stats["encounters"] = len(enc_list)

    for enc_name, items in enc_list:
        if not isinstance(items, list):
            continue

        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue

            stats["total_items"] += 1

            speaker = item.get("speaker", "")
            text    = item.get("text",    "")
            chatter = item.get("chatter", "")

            # ── speaker ──
            if speaker:
                if should_skip_speaker(speaker):
                    if RE_GAME_TAG.match(speaker.strip()):
                        stats["skipped_tag"] += 1
                else:
                    result.append({
                        "key":         f"{enc_name}[{idx}].speaker",
                        "original":    speaker.strip(),
                        "translation": "",
                        "stage":       0,
                        "context":     f"说话人 | {enc_name}",
                    })
                    stats["extracted"] += 1

            # ── text ──
            if text:
                if should_skip_text(text):
                    stats["skipped_blank"] += 1
                else:
                    entry = {
                        "key":         f"{enc_name}[{idx}].text",
                        "original":    text,
                        "translation": "",
                        "stage":       0,
                    }
                    ctx = []
                    # 只有真实说话人才加入 context
                    if speaker and not should_skip_speaker(speaker):
                        ctx.append(f"说话人: {speaker}")
                    ctx.append(f"{enc_name} 第{idx+1}条")
                    entry["context"] = " | ".join(ctx)
                    result.append(entry)
                    stats["extracted"] += 1

            # ── chatter ──
            if chatter:
                if should_skip_text(chatter):
                    stats["skipped_blank"] += 1
                else:
                    entry = {
                        "key":         f"{enc_name}[{idx}].chatter",
                        "original":    chatter,
                        "translation": "",
                        "stage":       0,
                        "context":     f"旁白 | {enc_name}",
                    }
                    result.append(entry)
                    stats["extracted"] += 1

    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"✅ 提取完成")
    print(f"   剧情数:          {stats['encounters']}")
    print(f"   总条目:          {stats['total_items']}")
    print(f"   待翻译:          {stats['extracted']}")
    print(f"   跳过(空/点号):   {stats['skipped_blank']}")
    print(f"   跳过(<游戏标签>):{stats['skipped_tag']}")
    print(f"   输出: {out_path}")


# ──────────────────────────────────────────────
# 回注
# ──────────────────────────────────────────────

def inject(src_path: str, translated_path: str, out_path: str,
           wrap_width: int = DEFAULT_WRAP_WIDTH, no_wrap: bool = False,
           dry_run: bool = False, verbose: bool = False,
           max_lines: int = DEFAULT_MAX_LINES, max_width: int = MAX_WIDTH_CAP,
           reflow: bool = True):
    print(f"读取原始: {src_path}")
    with open(src_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"读取译文: {translated_path}")
    with open(translated_path, "r", encoding="utf-8") as f:
        trans_list = json.load(f)

    # key → translation
    trans_map: dict[str, str] = {}
    skipped_empty = 0
    for item in trans_list:
        key   = item.get("key", "")
        trans = item.get("translation", "").strip()
        if key and trans:
            trans_map[key] = trans
        elif key:
            skipped_empty += 1

    print(f"   有效译文: {len(trans_map)} 条  |  未翻译(空): {skipped_empty} 条")

    # 解析 key：ENC_NAME[idx].field
    RE_KEY = re.compile(r'^(.+)\[(\d+)\]\.(text|speaker|chatter)$')

    count         = 0
    missing       = 0
    wrap_count    = 0    # 换行发生了变化的条目数
    overflow_list = []   # 排版后仍超过 max_lines 的条目: (key, 行数)
    wrap_details  = []   # 换行详情（verbose 用）

    # max_lines 传 0 视为不限制
    effective_max_lines = max_lines if max_lines else None

    for key, translation in trans_map.items():
        m = RE_KEY.match(key)
        if not m:
            print(f"  ⚠ 无法解析: {key}")
            continue

        enc_name = m.group(1)
        idx      = int(m.group(2))
        field    = m.group(3)

        enc_items = data.get(enc_name)
        if enc_items is None or idx >= len(enc_items):
            missing += 1
            continue
        if not isinstance(enc_items[idx], dict):
            missing += 1
            continue

        # ── 换行处理 ──
        # 对 text 和 chatter 字段自动换行（speaker 通常很短，不需要换行）
        do_wrap = (not no_wrap) and field in ("text", "chatter")
        processed, was_changed, exceeds = process_translation(
            translation, width=wrap_width, no_wrap=not do_wrap,
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
                "before": translation,
                "after": processed,
            })

        enc_items[idx][field] = processed
        count += 1

    # ── 输出 ──
    if dry_run:
        print(f"\n🔍 [DRY-RUN] 预览模式，不写入文件")
    else:
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 回注{'预览' if dry_run else '完成'}")
    print(f"   成功回注:     {count} 条")
    print(f"   换行/重排:    {wrap_count} 条  "
          f"(起始宽度≤{wrap_width}字，{'已启用' if reflow else '未启用'}合并重排)")
    print(f"   key失配:      {missing} 条")
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
            # 逐行展示
            for j, line in enumerate(detail['after'].split('\n')):
                print(f"      行{j+1} ({len(line)}字): {line}")
            if i < len(wrap_details):
                print()


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="ToA encounters.json 提取/回注工具 v4",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p1 = sub.add_parser("extract", help="提取可翻译文本")
    p1.add_argument("input")
    p1.add_argument("--output", "-o", default="encounters_paratranz.json")

    p2 = sub.add_parser("inject", help="将译文回注进 encounters.json")
    p2.add_argument("source")
    p2.add_argument("translated")
    p2.add_argument("--output", "-o", default="encounters_translated.json")
    p2.add_argument("--wrap", type=int, default=DEFAULT_WRAP_WIDTH,
                     help=f"起始换行宽度，超长译文自动添加换行符（默认 {DEFAULT_WRAP_WIDTH}）")
    p2.add_argument("--no-wrap", action="store_true", default=False,
                     help="禁用自动换行（仅处理字面 \\n 转换）")
    p2.add_argument("--max-lines", type=int, default=DEFAULT_MAX_LINES,
                     help=f"对话框最多显示行数，超出部分游戏里看不到"
                          f"（默认 {DEFAULT_MAX_LINES}，传 0 表示不限制）")
    p2.add_argument("--max-width", type=int, default=MAX_WIDTH_CAP,
                     help=f"放宽换行宽度的硬上限，超过会横向超出对话框（默认 {MAX_WIDTH_CAP}）")
    p2.add_argument("--no-reflow", dest="reflow", action="store_false", default=True,
                     help="禁用合并重排，恢复为仅对超长行追加换行（不会合并已有的 \\n）")
    p2.add_argument("--dry-run", action="store_true", default=False,
                     help="预览模式：只显示换行效果，不写入文件")
    p2.add_argument("--verbose", "-v", action="store_true", default=False,
                     help="显示每条换行的详细前后对比")

    args = parser.parse_args()

    if args.command == "extract":
        extract(args.input, args.output)
    elif args.command == "inject":
        inject(args.source, args.translated, args.output,
               wrap_width=args.wrap, no_wrap=args.no_wrap,
               dry_run=args.dry_run, verbose=args.verbose,
               max_lines=args.max_lines, max_width=args.max_width,
               reflow=args.reflow)


if __name__ == "__main__":
    main()
