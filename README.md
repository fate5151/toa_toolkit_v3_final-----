# ToA 汉化工具包 v4

**游戏**：Tales of Androgyny v0.3.69.0_Win64
**项目**：https://majalis.itch.io/tales-of-androgyny
**发布**：https://itch.io/t/6479954/03691-deepseek-v4-flash

---

## v4 更新说明

相对 v3，本次主要解决"游戏内对话框文字显示不全"的问题：

| 问题 | v4 解决方式 |
|------|------|
| 默认行宽偏窄，行尾留白过多 | 行宽 28→**32** 字（按实测对话框宽度估算） |
| 译文沿用原文/模型的旧换行位置，断行长短不均 | 新增**合并重排（reflow）**：先拼掉旧 `\n`，按新行宽重新断行 |
| 对话框最多显示 5 行，超出部分游戏里直接看不到 | 新增**最大行数控制**：超 5 行时自动尝试放宽行宽（最多到 34 字）压缩行数 |
| 放宽行宽也压不进 5 行的极端长译文 | 自动生成 `*.overflow.txt` 报告，列出需要人工精简的条目 |

旧版（仅对超长行追加换行、不合并旧换行）行为可通过 `--no-reflow` 恢复。

---

## 脚本清单

| 脚本 | 功能 |
|------|------|
| `textwrap_utils.py` | **共享换行模块** — 占位符保护、英文单词保护、智能标点断行、合并重排、最大行数控制 |
| `toa_trans_toolkit.py` | strings.properties 提取 / 回注 |
| `encounters_toolkit.py` | encounters.json 提取 / 回注 |
| `split_tool.py` | 去重 + 分批 / 合并（AiNiee 大文件处理）|
| `update_tool.py` | 版本更新增量翻译（缓存管理）|

---

## 完整工作流

### 首次翻译

```bash
# 1. 提取
python toa_trans_toolkit.py extract-strings strings.properties --fmt ainiee
python encounters_toolkit.py extract encounters.json

# 2. 分批（AiNiee 导入用）
python split_tool.py split strings_ainiee.json --size 5000 --no-context
python split_tool.py split encounters_paratranz.json --size 3000 --no-context

# 3. AiNiee 翻译所有 part_*.json（ParaTranz导出模式）

# 4. 合并
python split_tool.py merge strings_ainiee_parts/      --output strings_merged.json
python split_tool.py merge encounters_paratranz_parts/ --output encounters_merged.json

# 5. 导入翻译缓存（供后续版本更新使用）
python update_tool.py init strings_merged.json encounters_merged.json

# 6. 回注（自动换行 + 最大行数控制，均为默认开启）
python toa_trans_toolkit.py inject-strings strings.properties strings_merged.json output/strings.properties
python encounters_toolkit.py inject encounters.json encounters_merged.json --output output/encounters.json
```

回注完成后，留意终端输出的 `⚠️ 排版后仍超过 5 行的条目` 提示——如果有，去对应的
`*.overflow.txt` 报告里找到那几条 key，**手动精简译文**后重新跑一次回注即可。
没有提示则说明全部条目排版正常，无需额外操作。

### 版本更新（增量翻译）

```bash
# 1. 用新版本的文件重新提取
python toa_trans_toolkit.py extract-strings new_strings.properties --fmt ainiee
python encounters_toolkit.py extract new_encounters.json

# 2. 对比差异，只找出新增/修改的条目
python update_tool.py diff new_strings_ainiee.json      --output strings_todo.json
python update_tool.py diff new_encounters_paratranz.json --output encounters_todo.json

# 3. AiNiee 只翻译 *_todo.json（数量很少）

# 4. 将新译文存入缓存
python update_tool.py apply strings_todo_translated.json encounters_todo_translated.json

# 5. 导出完整回注文件
python update_tool.py export --output final_for_inject.json

# 6. 回注（自动换行 + 最大行数控制）
python toa_trans_toolkit.py inject-strings new_strings.properties final_for_inject.json output/strings.properties
python encounters_toolkit.py inject new_encounters.json final_for_inject.json --output output/encounters.json
```

---

## 换行功能详解

回注时自动处理译文换行，解决游戏中文本一行显示不全、或总行数超出对话框可视范围的问题。

### 核心特性

| 特性 | 说明 |
|------|------|
| **占位符保护** | `{0}`、`{nom0}`、`{poss0}`、`{Nom:ogre}` 等绝不被断开 |
| **英文单词保护** | 不会在 `Dark`、`Knight`、`attack` 等英文单词中间断行 |
| **中文标点智能断行** | 优先在 `，。！？；：` 等标点后断行，阅读更自然 |
| **合并重排（reflow）** | **默认开启**。先拼掉译文中已有的 `\n`，再统一按行宽重新断行，避免断行长短不一、行尾留白过多 |
| **最大行数控制** | 默认对话框最多 5 行；超出时自动尝试放宽行宽（最多到 34 字）压缩行数；仍压不进则记录到 overflow 报告 |
| **多层转义处理** | `\\n` → `\n` → 实际换行，层层还原 |
| **可配置行宽** | 默认每行 ≤28→**32** 字，适合游戏对话框 |

### 命令行参数

`encounters_toolkit.py inject` 和 `toa_trans_toolkit.py inject-strings` 共用以下参数：

```bash
--wrap N        起始换行宽度（默认 32）
--max-lines N   对话框最多显示行数（默认 5；传 0 表示不限制行数）
--max-width N   放宽行宽的硬上限（默认 34，超过会横向超出对话框）
--no-reflow     禁用合并重排，恢复为仅对超长行追加换行（保留原有 \n 位置）
--no-wrap       完全禁用自动换行（仅处理字面 \n → 真换行的转换）
--dry-run       预览模式：只显示换行效果和 overflow 统计，不写入任何文件
--verbose / -v  显示每条被改动条目的换行前后对比
```

示例：

```bash
# 默认参数（起始32字，最多5行，超限放宽到34字）
python encounters_toolkit.py inject encounters.json translated.json --output output.json

# 自定义起始宽度和最大行数
python encounters_toolkit.py inject encounters.json translated.json --output output.json --wrap 30 --max-lines 6

# 不限制行数，只做合并重排
python encounters_toolkit.py inject encounters.json translated.json --output output.json --max-lines 0

# 恢复 v3 旧行为（不合并已有换行，只对超长行追加断行）
python encounters_toolkit.py inject encounters.json translated.json --output output.json --no-reflow

# 预览模式：只看换行/超限统计，不落盘
python encounters_toolkit.py inject encounters.json translated.json --output output.json --dry-run --verbose
```

`toa_trans_toolkit.py inject-strings` 同样支持以上所有参数。

### 换行效果示例

```
原译文（已有旧换行，长短不均，行尾留白多）：
你突然变得僵硬，无法动弹四肢—你并非摔倒在地，
而是被她用尾巴的沟槽接住，举了起来。
你甚至无法转头往下看，但感觉到脚边一片湿漉漉……
那触感竟出乎意料地熟悉。
（共4行，最后两行明显偏短）

reflow 后（合并旧换行，按32字重新断行）：
你突然变得僵硬，无法动弹四肢—你并非摔倒在地，
而是被她用尾巴的沟槽接住，举了起来。你甚至无法转头往下看，
但感觉到脚边一片湿漉漉……那触感竟出乎意料地熟悉。
（压缩为3行，每行字数更均匀）
```

```
含占位符的文本（不会被断开）：
原文：你用{weapon}击中了{Nom:ogre}，造成了{0}点伤害！
换行：你用{weapon}击中了{Nom:ogre}，造成了\n{0}点伤害！
      ↑ 占位符完整保留，不会被拆分
```

```
超长译文压缩示例（放宽行宽以减少行数）：
按32字断行 → 7行（超出5行限制）
放宽到34字断行 → 5行（恰好压进限制，不再触发 overflow 报告）
若放宽到34字仍超过5行 → 记录进 *.overflow.txt，需人工精简该条译文
```

### overflow 报告

回注完成后，若有条目排版后仍超过 `--max-lines` 限制，终端会打印：

```
⚠️ 排版后仍超过 5 行的条目（已尝试放宽至34字仍超出，需人工精简译文）: N 条
   ENCOUNTER-NAME[12].text  (7 行)
   ...
   完整列表已写入: output/encounters.json.overflow.txt
```

`*.overflow.txt` 格式为 `key<TAB>行数`，按这个列表去对应的译文文件中找到这些 key，
精简文字后重新跑一次回注命令覆盖输出即可，不需要重新跑提取/分批/合并等前置步骤。

---

## 游戏翻译包目录结构

```
translations/
  zh/
    manifest.json
    assets/
      translation/
        strings.properties   ← 回注后放这里
      script/
        encounters.json      ← 回注后放这里
```

## manifest.json

```json
{
  "languageName": "简体中文",
  "localeId": "zh"
}
```

---

## AiNiee 设置

- 导入格式：**ParaTranz导出**
- API：`https://api.deepseek.com`
- 模型：`deepseek-v4-flash`
- 译文字段：`translation`

---

## 注意事项

- `{0}` `{nom0}` `{poss0}` `{Nom:ogre}` 等占位符**原样保留**，换行时绝不断开
- `<DARK_KNIGHT>` 等 `<角色标签>` 格式已自动过滤，无需翻译
- `speaker=Hiro` 已自动跳过（游戏运行时替换玩家名）
- `trans_cache.json` 是核心翻译缓存，**务必备份**
- 回注默认启用**合并重排**：会先拼掉译文里已有的 `\n`，再按行宽统一重新断行
  - 如果想保留译者/模型已有的换行位置（不合并），加 `--no-reflow`
- 回注默认启用**最大行数控制**（5 行）：超限会自动放宽行宽（最多到 34 字）压缩行数
  - 仍超限的条目会写入 `*.overflow.txt`，需要人工精简译文后重新回注
  - 不需要行数限制时加 `--max-lines 0`
  - AiNiee 译文中的字面 `\n`（反斜杠+n）会自动转换为实际换行符
  - 英文单词不会被从中间断开（如 `Extraordinary` 保持完整）
