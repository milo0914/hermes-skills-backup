#!/usr/bin/env python3
"""
Merck KGaA 負介電液晶專利搜索 (v2 - 改進版)
改進重點：
1. 使用正確的日期範圍語法：filing_date:>=2020-01-01 AND filing_date:<=2026-12-31
2. 加入 CPC 分類代碼：C09K19/30 (負介電液晶材料)
3. 使用布林運算符：AND, OR, NOT 和括號分組
4. 加入同義詞擴展：negative dielectric anisotropy, Δε < 0, negative delta epsilon
5. 使用精確匹配短語
"""

from firecrawl import FirecrawlApp
import os
import json
from datetime import datetime

# 檢查 API Key
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")
if not FIRECRAWL_API_KEY:
    print("❌ 錯誤：FIRECRAWL_API_KEY 未設置")
    exit(1)

app = FirecrawlApp(api_key=FIRECRAWL_API_KEY)

# 改進後的搜索策略
search_queries = [
    # 策略 1: CPC 分類 + 日期範圍 + Merck KGaA
    {
        "name": "CPC + 日期範圍 + Merck",
        "query": "cpc:C09K19/30 AND filing_date:>=2020-01-01 AND filing_date:<=2026-12-31 AND (Merck OR Merck KGaA)"
    },
    # 策略 2: 負介電各向異性 + 日期範圍 + Merck
    {
        "name": "負介電 + 日期範圍 + Merck",
        "query": "(filing_date:>=2020-01-01 AND filing_date:<=2026-12-31) AND (Merck OR Merck KGaA) AND (\"negative dielectric anisotropy\" OR \"negative dielectric constant\" OR \"Δε < 0\" OR \"delta epsilon < 0\")"
    },
    # 策略 3: 液晶材料 + 日期範圍 + Merck
    {
        "name": "液晶 + 日期範圍 + Merck",
        "query": "(filing_date:>=2020-01-01 AND filing_date:<=2026-12-31) AND (Merck OR Merck KGaA) AND (\"liquid crystal\" OR \"liquid crystalline\") AND (negative OR fluorine OR halogen)"
    },
    # 策略 4: VA/IPS 模式 + 日期範圍 + Merck
    {
        "name": "VA/IPS 模式 + 日期範圍 + Merck",
        "query": "(filing_date:>=2020-01-01 AND filing_date:<=2026-12-31) AND (Merck OR Merck KGaA) AND (\"VA mode\" OR \"IPS mode\" OR \"vertical alignment\" or \"in-plane switching\")"
    }
]

# 執行搜索
print("=" * 80)
print("Merck KGaA 負介電液晶專利搜索 (v2 - 改進版)")
print("=" * 80)
print(f"搜索時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"日期範圍：2020-01-01 至 2026-12-31")
print(f"CPC 分類：C09K19/30 (負介電液晶材料)")
print("=" * 80)

all_results = []
seen_urls = set()

for i, search_config in enumerate(search_queries, 1):
    print(f"\n[{i}/{len(search_queries)}] 執行搜索：{search_config['name']}")
    print(f"查詢：{search_config['query']}")
    
    try:
        # 使用 Firecrawl 搜索
        results = app.search(
            query=search_config['query'],
            limit=15
        )
        
        # 從 SearchData 中提取 web 結果
        web_results = []
        if hasattr(results, 'web') and results.web:
            web_results = results.web
        elif hasattr(results, '__dict__') and 'web' in results.__dict__:
            web_results = results.__dict__.get('web', [])
        
        print(f"找到 {len(web_results)} 筆 web 結果")
        
        # 處理結果
        for result in web_results:
            # 訪問 SearchResultWeb 對象的屬性
            url = result.url if hasattr(result, 'url') else ''
            title = result.title if hasattr(result, 'title') else ''
            description = result.description if hasattr(result, 'description') else ''
            
            # 過濾重復
            if url in seen_urls:
                continue
            
            # 只保留專利相關連結
            if any(x in url for x in ["patents.google.com", "patents.justia.com", "ipqwery.com", "worldwide.espacenet.com"]):
                seen_urls.add(url)
                all_results.append({
                    "url": url,
                    "title": title,
                    "description": description,
                    "source": search_config['name'],
                    "query": search_config['query']
                })
                print(f"  ✓ 新增：{title[:80]}")
        
    except Exception as e:
        print(f"  ✗ 搜索失敗：{e}")
        all_results.append({
            "error": str(e),
            "query": search_config['query']
        })

# 保存結果
print(f"\n總計找到 {len(all_results)} 個唯一專利")
output_file = "/tmp/patent_search_results_v2.json"
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(all_results, f, indent=2, ensure_ascii=False)

print(f"結果已保存至：{output_file}")

# 顯示統計
print("\n" + "=" * 80)
print("搜索統計")
print("=" * 80)
sources = {}
for result in all_results:
    source = result.get('source', 'Unknown')
    sources[source] = sources.get(source, 0) + 1

for source, count in sources.items():
    print(f"{source}: {count} 個專利")

print("\n" + "=" * 80)
print("下一步：執行專利提取")
print("=" * 80)
