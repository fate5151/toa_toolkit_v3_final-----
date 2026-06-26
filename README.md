# ToA 汉化工具包 v3 (最终版)

**游戏**：Tales of Androgyny v0.3.67.0  
**项目**：https://majalis.itch.io/tales-of-androgyny  
**发布**：https://itch.io/t/6479954/03691-deepseek-v4-flash

---

## 脚本清单

| 脚本 | 功能 |
|------|------|
| `textwrap_utils.py` | **共享换行模块** — 占位符保护、英文单词保护、智能标点断行 |
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

# 6. 回注（自动换行）
python toa_trans_toolkit.py inject-strings strings.properties strings_merged.json output/strings.properties
python encounters_toolkit.py inject encounters.json encounters_merged.json --output output/encounters.json
```

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

# 6. 回注（自动换行）
python toa_trans_toolkit.py inject-strings new_strings.properties final_for_inject.json output/strings.properties
python encounters_toolkit.py inject new_encounters.json final_for_inject.json --output output/encounters.json
```

---

## 换行功能详解

回注时自动为长译文添加 `\n` 换行符，解决游戏中文本一行显示不全的问题。

### 核心特性

| 特性 | 说明 |
|------|------|
| **占位符保护** | `{0}`、`{nom0}`、`{poss0}`、`{Nom:ogre}` 等绝不被断开 |
| **英文单词保护** | 不会在 `Dark`、`Knight`、`attack` 等英文单词中间断行 |
| **中文标点智能断行** | 优先在 `，。！？；：` 等标点后断行，阅读更自然 |
| **多层转义处理** | `\\n` → `\n` → 实际换行，层层还原 |
| **尊重已有换行** | 保留译者手动换行，仅对超长行再断行 |
| **可配置行宽** | 默认 28 字，适合游戏对话框 |

### 命令行参数

```bash
# 默认：每行≤28字自动换行
python encounters_toolkit.py inject encounters.json translated.json --output output.json

# 自定义每行30字
python encounters_toolkit.py inject encounters.json translated.json --output output.json --wrap 30

# 禁用自动换行（仅转换字面 \n）
python encounters_toolkit.py inject encounters.json translated.json --output output.json --no-wrap

# 预览模式：只显示换行效果，不写入文件
python encounters_toolkit.py inject encounters.json translated.json --output output.json --dry-run

# 详细模式：显示每条换行的前后对比
python encounters_toolkit.py inject encounters.json translated.json --output output.json --verbose
```

`toa_trans_toolkit.py inject-strings` 同样支持以上所有参数。

### 换行效果示例

```
原文（43字，一行显示不全）：
冰冷的水珠不再令人清爽，它们刺痛你的皮肤，贪婪吮吸体温，你睫毛上抖落的水珠像极了泪水。

换行后（在逗号处断行）：
行1 (28字): 冰冷的水珠不再令人清爽，它们刺痛你的皮肤，贪婪吮吸体温，
行2 (15字): 你睫毛上抖落的水珠像极了泪水。
```

```
含占位符的文本（不会被断开）：
原文：你用{weapon}击中了{Nom:ogre}，造成了{0}点伤害！
换行：你用{weapon}击中了{Nom:ogre}，造成了\n{0}点伤害！
      ↑ 占位符完整保留，不会被拆分
```

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
- 模型：`deepseek-v4-pro`
- 译文字段：`translation`

---

## 注意事项

- `{0}` `{nom0}` `{poss0}` `{Nom:ogre}` 等占位符**原样保留**，换行时绝不断开
- `<DARK_KNIGHT>` 等 `<角色标签>` 格式已自动过滤，无需翻译
- `speaker=Hiro` 已自动跳过（游戏运行时替换玩家名）
- `trans_cache.json` 是核心翻译缓存，**务必备份**
- 回注时自动为长译文添加 `\n` 换行符，避免游戏中文本一行显示不全
  - 默认每行≤28字，优先在中文标点（，。！？等）后断行
  - `--wrap N` 可调整每行最大字数，`--no-wrap` 可禁用自动换行
  - `--dry-run` 预览换行效果，`--verbose` 显示详细前后对比
  - AiNiee 译文中的字面 `\n`（反斜杠+n）会自动转换为实际换行符
  - 英文单词不会被从中间断开（如 `Extraordinary` 保持完整）
