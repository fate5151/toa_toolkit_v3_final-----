#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ToA 汉化工具包 — 智能换行模块 v2
================================
为游戏回注译文自动添加换行符（\\n），解决长文本一行显示不全的问题。

v2 更新内容：
  - 默认行宽从 28 调整为 32 字（按对话框实测宽度估算）
  - 新增 reflow_text()：先合并已有换行再统一重新断行，
    解决"断行长短不一、留白过多"的问题
  - 新增最大行数控制（DEFAULT_MAX_LINES）：对话框最多显示 N 行，
    超出部分游戏里看不到；排版时会在 [width, max_width] 区间内
    尝试放宽行宽以压缩行数
  - process_translation() 现在返回三元组：
    (处理后文本, 换行是否发生变化, 是否仍超过最大行数)
    —— 调用处需要同步修改解包方式！

核心特性（沿用 v1）：
  - 占位符保护：{0}、{nom0}、{poss0}、{Nom:ogre} 等绝不被断开
  - 英文单词保护：不会在英文单词中间断行
  - 中文标点智能断行：优先在 ，。！？ 等标点后断行
  - 多层转义处理：\\n → \\n → 实际换行，层层还原

被 encounters_toolkit.py 和 toa_trans_toolkit.py 共同引用。
"""

import re

# ──────────────────────────────────────────────
# 常量
# ──────────────────────────────────────────────

# 默认每行最大字符数（中文，适合游戏对话框；按实测宽度估算）
DEFAULT_WRAP_WIDTH = 40

# 对话框最多显示行数，超出部分游戏里看不到
DEFAULT_MAX_LINES = 5

# 放宽断行宽度的硬上限：超过这个数字文字会顶出对话框，不能再放宽
# 注意：必须 >= DEFAULT_WRAP_WIDTH，否则"超5行自动放宽"的保险机制会失效
MAX_WIDTH_CAP = 42

# 中文标点：优先在这些字符之后断行（断行后标点留在上一行末尾）
BREAK_AFTER = frozenset("，。！？；：、」）》」』】…—～~,.!?;:")

# 中文标点：优先在这些字符之前断行（断行后标点出现在新行开头）
BREAK_BEFORE = frozenset("「《『【(")

# 占位符正则：
#   - 花括号 {0}、{nom0}、{poss0}、{Nom:ogre}、{1:format} 等数据占位符
#   - 方括号 [heartbeat=.2]、[endheartbeat]、[%150]、[crowd=5;5]、[endcrowd] 等
#     游戏引擎的语音/特效控制标签（心跳音效计时、文字缩放、人群特效等）
# 两者都绝不能被换行符切断，否则进游戏后标签失效甚至显示乱码
RE_PLACEHOLDER = re.compile(r'\{[^{}]*\}|\[[^\[\]]*\]')

# 英文单词正则：连续的英文字母和撇号
RE_ENGLISH_WORD = re.compile(r"[A-Za-z][A-Za-z']*")


def _is_ascii_alpha(ch: str) -> bool:
    """判断字符是否为 ASCII 字母（A-Z, a-z）。

    注意：Python 的 str.isalpha() 对中文字符也返回 True，
    所以不能用它来判断英文单词边界。
    """
    return 'A' <= ch <= 'Z' or 'a' <= ch <= 'z'


# ──────────────────────────────────────────────
# 占位符保护
# ──────────────────────────────────────────────

def _protect_placeholders(text: str) -> tuple[str, dict[str, str]]:
    """将 {占位符} 替换为不可断开的标记，返回 (处理后文本, 映射表)。

    这样断行算法不会在占位符中间插入换行符。
    标记使用 \\x01 填充至与原占位符等长或更长，确保：
      - 字符计数不会少于原占位符（还原后行宽不会超限）
      - 标记永远不会被截断（保证还原正确性）
    """
    placeholders = {}
    counter = [0]

    def _replace(m):
        original = m.group(0)
        # 标记格式：\x00 + 序号 + \x00，保证唯一且可还原
        key = f"\x00{counter[0]}\x00"
        # 如果原占位符比标记长，用 \x01 填充到等长（保证字符计数准确）
        # 如果原占位符比标记短，保留标记原样（保守换行，还原后行宽只会更短）
        if len(original) > len(key):
            key += "\x01" * (len(original) - len(key))
        placeholders[key] = original
        counter[0] += 1
        return key

    protected = RE_PLACEHOLDER.sub(_replace, text)
    return protected, placeholders


def _restore_placeholders(text: str, placeholders: dict[str, str]) -> str:
    """将标记还原为原始占位符。"""
    for key, original in placeholders.items():
        text = text.replace(key, original)
    return text


# ──────────────────────────────────────────────
# 换行符标准化
# ──────────────────────────────────────────────

def normalize_newlines(text: str) -> str:
    r"""将译文中的各种换行表示统一为实际换行符。

    处理以下情况：
      - 字面 \n（两个字符：反斜杠 + n）→ 实际换行
      - 双重转义 \\n（四个字符）→ 先还原为 \n，再转为实际换行
      - <br> / <br/> HTML 换行标签 → 实际换行
      - \r\n Windows 换行 → \n
    """
    if not text:
        return text

    # 1. HTML 换行标签
    text = re.sub(r'<br\s*/?\s*>', '\n', text)

    # 2. Windows 换行
    text = text.replace('\r\n', '\n')
    text = text.replace('\r', '\n')

    # 3. 双重转义 \\n → 先变成 \n（字面），再变成实际换行
    #    注意顺序：先处理长的，再处理短的
    text = text.replace('\\\\n', '\n')

    # 4. 字面 \n（反斜杠 + n）→ 实际换行
    text = text.replace('\\n', '\n')

    return text


# ──────────────────────────────────────────────
# 智能断行
# ──────────────────────────────────────────────

def wrap_text(text: str, width: int = DEFAULT_WRAP_WIDTH) -> str:
    """为长文本自动添加换行符，优先在标点处断行。

    规则：
      - 如果文本已包含换行符，保留原有换行，仅对超长的单行再做断行
      - 占位符 {0}、{nom0} 等绝不被断开
      - 英文单词不会被从中间断开
      - 优先在中文标点后断行
      - 其次在中文标点前断行
      - 其次在空格处断行
      - 最后才硬断行

    注意：本函数不会合并已有的换行，只对每个已有段落独立判断是否超宽。
    如果需要先合并旧换行再统一重排（修正断行长短不一、留白过多的问题），
    请使用 reflow_text()。
    """
    if not text:
        return text

    # 先按已有换行符分段，逐段处理
    paragraphs = text.split('\n')
    result = []

    for para in paragraphs:
        if len(para) <= width:
            result.append(para)
            continue

        # 对超长段落逐行切分
        lines = _split_paragraph(para, width)
        result.extend(lines)

    return '\n'.join(result)


def reflow_text(text: str, width: int = DEFAULT_WRAP_WIDTH,
                 max_lines: int | None = DEFAULT_MAX_LINES,
                 max_width: int = MAX_WIDTH_CAP) -> tuple[str, int, bool]:
    r"""合并已有换行后按 width 重新断行，并尽量控制最大行数。

    适用场景：
      译文中已经包含 \n（可能来自原文行宽、或翻译模型沿用了原文
      换行位置），导致断行长短不一、行尾留白过多、或总行数超过
      对话框最多可显示的行数（多出来的行游戏里直接看不到）。

    策略：
      1. 把文本里已有的 \n 全部拼掉（中文不需要空格分词，直接拼接）
      2. 按 width 重新断行
      3. 若行数仍超过 max_lines，逐步放宽 width 重试
         （框够宽时，断行次数减少，能省下一整行）
      4. 放宽到 max_width 仍超出 → 排版已无法再压缩，
         说明译文本身偏长，需要人工精简；此时仍返回当前最佳排版结果，
         并将 still_exceeds 标记为 True，供上层统计/生成报告

    参数：
      text:      原始译文（可能含 \n）
      width:     起始换行宽度
      max_lines: 最大允许行数，None 或 0 表示不限制行数
      max_width: 放宽宽度的硬上限（超过会横向顶出对话框）

    返回：
      (处理后文本, 实际使用的宽度, 是否仍超过 max_lines)
    """
    if not text:
        return text, width, False

    merged = text.replace('\n', '')
    current_width = width
    result = wrap_text(merged, width=current_width)

    if not max_lines:
        return result, current_width, False

    while (result.count('\n') + 1) > max_lines and current_width < max_width:
        current_width += 1
        result = wrap_text(merged, width=current_width)

    still_exceeds = (result.count('\n') + 1) > max_lines
    return result, current_width, still_exceeds


def _split_paragraph(para: str, width: int) -> list:
    """将一个超长段落切分为多行。"""
    # 保护占位符
    protected, placeholders = _protect_placeholders(para)

    lines = []
    remaining = protected

    while len(remaining) > width:
        cut_pos = _find_break_point(remaining, width)
        # 安全检查：确保断点不在占位符标记内部
        cut_pos = _adjust_for_placeholder(remaining, cut_pos)

        line = remaining[:cut_pos].rstrip()
        remaining = remaining[cut_pos:].lstrip()

        # 防止无限循环：如果断行后剩余为空，直接追加
        if not remaining:
            lines.append(line)
            break

        lines.append(line)

    if remaining:
        lines.append(remaining)

    # 还原占位符
    lines = [_restore_placeholders(line, placeholders) for line in lines]

    return lines


def _adjust_for_placeholder(text: str, pos: int) -> int:
    """如果断点落在占位符标记内部，调整到标记结束位置之后。

    标记格式：\\x00 + 序号(数字) + \\x00 + \\x01填充
    确保不在标记中间断行。

    策略：扫描文本中所有标记的范围，如果 pos 落在某个标记内部，
    则将断点调整到该标记结束位置之后。
    """
    i = 0
    while i < len(text):
        if text[i] == '\x00':
            # 可能是标记起始
            j = i + 1
            while j < len(text) and text[j].isdigit():
                j += 1
            if j < len(text) and text[j] == '\x00':
                # 确认是标记：\x00 + digits + \x00
                j += 1  # 跳过结束 \x00
                # 跳过 \x01 填充
                while j < len(text) and text[j] == '\x01':
                    j += 1
                # 标记范围：[i, j)
                if i < pos < j:
                    # pos 在标记内部，调整到标记结束之后
                    return j
                i = j
            else:
                i += 1
        else:
            i += 1
    return pos


def _find_break_point(text: str, width: int) -> int:
    """在 text[:width] 范围内寻找最佳断行位置。

    策略：在 [width * 0.5, width] 范围内寻找最靠近 width 的断行点。
    这样既避免行太短，又不会超出宽度限制。

    优先级：
      1. 中文标点后断行（BREAK_AFTER 中的字符之后）
      2. 中文标点前断行（BREAK_BEFORE 中的字符之前）
      3. 空格处断行
      4. 英文单词边界处断行
      5. 占位符边界处断行（\x00 标记的边界）
      6. 无合适断行点时硬断行
    """
    # 搜索范围：至少从 width 的一半开始，避免行太短
    min_pos = max(1, width // 2)
    max_pos = min(width, len(text))
    search_range = text[min_pos:max_pos]

    # 1. 优先在标点后断行：在搜索范围内找最靠后（最接近 width）的标点
    best_after = -1
    for i in range(len(search_range) - 1, -1, -1):
        actual_pos = min_pos + i
        if text[actual_pos] in BREAK_AFTER:
            best_after = actual_pos + 1  # 在标点之后断行
            break

    # 2. 在标点前断行
    best_before = -1
    for i in range(len(search_range) - 1, -1, -1):
        actual_pos = min_pos + i
        if text[actual_pos] in BREAK_BEFORE:
            best_before = actual_pos  # 在标点之前断行
            break

    # 3. 空格处断行
    best_space = -1
    for i in range(len(search_range) - 1, -1, -1):
        actual_pos = min_pos + i
        if text[actual_pos] == ' ':
            best_space = actual_pos
            break

    # 4. 英文单词边界：避免在英文单词中间断行
    # 注意：只用 ASCII 字母判断，因为 Python 的 isalpha() 对中文也返回 True
    best_word_boundary = -1
    if max_pos < len(text):
        # 检查 max_pos 位置是否在英文单词中间
        if _is_ascii_alpha(text[max_pos - 1]) and _is_ascii_alpha(text[max_pos]):
            # max_pos 在英文单词中间，向前找单词开头
            word_start = -1
            for i in range(max_pos - 1, -1, -1):
                if not _is_ascii_alpha(text[i]):
                    word_start = i + 1
                    break
            if word_start < 0:
                word_start = 0
            # 在单词前断行（行会变短，但不会断开单词）
            if word_start > 0:
                best_word_boundary = word_start
            # 如果单词从行首开始，无法在单词前断行，只能硬断行

    # 5. 占位符边界：在 \x00 标记边界处断行
    best_ph_boundary = -1
    for i in range(len(search_range) - 1, -1, -1):
        actual_pos = min_pos + i
        # 在占位符标记的 \x01 填充末尾或 \x00 起始处断行
        if text[actual_pos] == '\x01' and (actual_pos + 1 >= len(text) or text[actual_pos + 1] != '\x01'):
            best_ph_boundary = actual_pos + 1
            break
        if text[actual_pos] == '\x00' and actual_pos > 0 and text[actual_pos - 1] != '\x00':
            best_ph_boundary = actual_pos
            break

    # 选择最佳断行点：标点后 > 标点前 > 空格 > 英文单词边界 > 占位符边界 > 硬断行
    candidates = []
    if best_after > 0:
        candidates.append(best_after)
    if best_before > 0:
        candidates.append(best_before)
    if best_space > 0:
        candidates.append(best_space)
    if best_word_boundary > 0:
        candidates.append(best_word_boundary)
    if best_ph_boundary > 0:
        candidates.append(best_ph_boundary)

    if candidates:
        # 选择最大的（最接近 width 的），避免行太短
        return max(candidates)

    # 6. 无合适断行点，硬断行
    return max_pos


# ──────────────────────────────────────────────
# 处理单条译文（供回注工具调用）
# ──────────────────────────────────────────────

def process_translation(text: str, width: int = DEFAULT_WRAP_WIDTH,
                         no_wrap: bool = False, reflow: bool = True,
                         max_lines: int | None = DEFAULT_MAX_LINES,
                         max_width: int = MAX_WIDTH_CAP) -> tuple[str, bool, bool]:
    """处理单条译文：标准化换行符 + 自动换行/重排 + 行数控制。

    参数：
      text:      原始译文
      width:     每行最大字符数（起始宽度）
      no_wrap:   是否禁用自动换行（仅做换行符标准化）
      reflow:    是否先合并已有换行再统一重排（默认开启，能修正
                 "断行长短不一、留白过多"的问题；如需保留译者/原文
                 已有的换行位置，可传 False 改为仅对超长行追加断行，
                 即 v1 的行为）
      max_lines: 对话框最多显示行数，None 或 0 表示不限制
      max_width: 放宽断行宽度的硬上限（仅在 reflow=True 时生效）

    返回：
      (处理后的文本, 换行是否发生了变化, 是否仍超过 max_lines)

    注意：本函数返回值是三元组（v1 是二元组），调用处需要相应解包。
    """
    if not text:
        return text, False, False

    # 1. 标准化换行符
    processed = normalize_newlines(text)

    # 2. 不换行：仅做标准化
    if no_wrap:
        return processed, False, False

    before = processed

    # 3. 合并重排 或 仅对超长行追加断行
    if reflow:
        processed, _used_width, exceeds = reflow_text(
            processed, width=width, max_lines=max_lines, max_width=max_width
        )
    else:
        processed = wrap_text(processed, width=width)
        exceeds = bool(max_lines) and ((processed.count('\n') + 1) > max_lines)

    changed = (processed != before)
    return processed, changed, exceeds


# ──────────────────────────────────────────────
# 独立使用：直接对 JSON 文件添加换行
# ──────────────────────────────────────────────

def wrap_json_file(input_path: str, output_path: str,
                    width: int = DEFAULT_WRAP_WIDTH,
                    text_key: str = "translation",
                    max_lines: int | None = DEFAULT_MAX_LINES,
                    max_width: int = MAX_WIDTH_CAP,
                    reflow: bool = True) -> dict:
    """对已有的翻译 JSON 文件中的译文添加换行符。

    适用于已经回注但忘记加换行（或需要调整行宽/最大行数限制）的情况，
    可以直接对翻译 JSON 处理。

    参数：
      input_path:  输入 JSON 文件路径
      output_path: 输出 JSON 文件路径
      width:       每行最大字符数
      text_key:    译文所在的字段名
      max_lines:   对话框最多显示行数，None 或 0 表示不限制
      max_width:   放宽断行宽度的硬上限
      reflow:      是否先合并已有换行再统一重排

    返回：
      统计信息字典
    """
    import json

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    total = 0
    wrapped = 0
    unchanged = 0
    overflow_keys = []

    for item in data:
        text = item.get(text_key, "")
        if not text or not text.strip():
            continue

        total += 1
        processed, was_changed, exceeds = process_translation(
            text, width=width, reflow=reflow, max_lines=max_lines, max_width=max_width
        )

        if exceeds:
            overflow_keys.append(item.get("key") or item.get("name") or text[:20])

        if was_changed:
            wrapped += 1
            item[text_key] = processed
        else:
            unchanged += 1

    import os
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return {
        "total": total,
        "wrapped": wrapped,
        "unchanged": unchanged,
        "overflow": len(overflow_keys),
        "overflow_keys": overflow_keys,
    }
