import json, os, glob

CACHE = "trans_cache.json"
# 自动寻找新提取的原文文件
files = [f for f in glob.glob("*.json") if "todo" not in f and "merged" not in f and "cache" not in f and ("ainiee" in f or "paratranz" in f)]

if not os.path.exists(CACHE):
    print("❌ 找不到 trans_cache.json"); exit()

with open(CACHE, "r", encoding="utf-8") as f: cache = json.load(f)

total = 0
for src in files:
    print(f"🔍 读取: {src}")
    data = json.load(open(src, encoding="utf-8"))
    c = 0
    for item in data:
        k, en = item.get("key"), item.get("original", "")
        if k in cache and cache[k].get("zh") and not cache[k].get("en", "").strip():
            cache[k]["en"] = en
            c += 1
    print(f"  ✅ 修复 {c} 条")
    total += c

with open(CACHE, "w", encoding="utf-8") as f: json.dump(cache, f, ensure_ascii=False, indent=2)
print(f"\n🎉 完成！共修复 {total} 条。")