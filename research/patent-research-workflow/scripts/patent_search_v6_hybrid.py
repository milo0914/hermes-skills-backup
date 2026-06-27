#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Merck KGaA 負介電液晶專利搜索 v6 - 混合方案（Firecrawl + Crawl4AI）
GRPO 規劃改進版 - 方案 C（評分 1.65/2.0）

改進策略:
1. Firecrawl 搜索獲取專利 URL 列表
2. Crawl4AI 批量爬取專利頁面 markdown
3. 手動解析 markdown 提取 Claim 1 和實施例
4. 嚴格日期過濾（2020-2026）

執行方式:
    python3 patent_search_v6_hybrid.py
"""

import json
import os
from datetime import datetime
from firecrawl import FirecrawlApp

# 初始化 Firecrawl
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")
if not FIRECRAWL_API_KEY:
    print("❌ 錯誤：FIRECRAWL_API_KEY 未設置")
    exit(1)

app = FirecrawlApp(api_key=FIRECRAWL_API_KEY)

def search_patents():
    """使用 Firecrawl 搜索專利"""
    print("=" * 80)
    print("Merck KGaA 負介電液晶專利搜索 v6（混合方案）")
    print("=" * 80)
    
    # 搜索關鍵字
    search_queries = [
        "Merck KGaA negative dielectric liquid crystal patent",
        "Merck negative dielectric anisotropy liquid crystal",
        "EMD negative dielectric liquid crystal patent",
        "Merck patent liquid crystal display 2020..2026"
    ]
    
    all_patents = []
    
    for query in search_queries:
        print(f"\n🔍 搜索：{query}")
        try:
            # Firecrawl 搜索
            results = app.search(
                query=query,
                limit=10
            )
            
            # 提取專利相關連結
            for result in results.get("data", []):
                url = result.get("url", "")
                # 只保留專利連結
                if any(x in url for x in ["patents.google.com", "patents.justia.com", "ipqwery.com"]):
                    patent = {
                        "url": url,
                        "title": result.get("title", ""),
                        "description": result.get("description", ""),
                        "search_query": query
                    }
                    # 避免重複
                    if patent not in all_patents:
                        all_patents.append(patent)
            
            print(f"  ✓ 找到 {len(results.get('data', []))} 個結果")
            
        except Exception as e:
            print(f"  ✗ 搜索失敗：{e}")
    
    print(f"\n總共找到 {len(all_patents)} 個專利連結")
    
    # 保存搜索結果
    search_data = {
        "search_time": datetime.now().isoformat(),
        "queries": search_queries,
        "patents": all_patents
    }
    
    with open("/tmp/patent_search_results_v6.json", "w", encoding="utf-8") as f:
        json.dump(search_data, f, indent=2, ensure_ascii=False, default=str)
    
    print(f"結果已保存：/tmp/patent_search_results_v6.json")
    
    return all_patents

if __name__ == "__main__":
    patents = search_patents()
    
    if patents:
        print("\n" + "=" * 80)
        print("✅ 搜索完成！")
        print(f"找到 {len(patents)} 個專利")
        print("\n下一步：執行提取腳本 patent_extract_v6_hybrid.py")
        print("=" * 80)
    else:
        print("\n❌ 未找到任何專利")
        exit(1)
