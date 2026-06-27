#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Patent Search Example Script - Firecrawl MCP
專利搜索完整範例 - 可直接執行的腳本

使用方式:
    export FIRECRAWL_API_KEY="fc-your-key"
    python patent_search_example.py

輸出:
    - /tmp/patent_search_results.json: 搜索結果
    - /tmp/extracted_patents_v2.json: 提取的專利詳情
    - /tmp/merck_negative_dielectric_patents_report_v2.md: Markdown 報告
"""

import os
import json
from datetime import datetime
from firecrawl import FirecrawlApp

# 配置
SEARCH_QUERIES = [
    "Merck KGaA negative dielectric liquid crystal patent 2020..2026",
    "Merck negative permittivity liquid crystal compound patent",
    "Merck KGaA Δε < 0 liquid crystal material patent",
    "Merck liquid crystal VA IPS FFS patent 2020..2026",
]
TARGET_COUNT = 15
OUTPUT_DIR = "/tmp"

def main():
    FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")
    if not FIRECRAWL_API_KEY:
        raise ValueError("請先設置 FIRECRAWL_API_KEY 環境變量")
    
    app = FirecrawlApp(api_key=FIRECRAWL_API_KEY)
    
    # 階段 1: 搜索
    print("階段 1: 搜索專利...")
    all_results = []
    seen_urls = set()
    
    for query in SEARCH_QUERIES:
        try:
            results = app.search(query=query, limit=10)
            for result in results.web:
                url = result.url
                if url not in seen_urls and any(x in url for x in ["patents.google.com", "patents.justia.com", "ipqwery.com"]):
                    seen_urls.add(url)
                    all_results.append({
                        "url": url,
                        "title": result.title,
                        "description": result.description
                    })
        except Exception as e:
            print(f"搜索失敗 {query}: {e}")
    
    print(f"找到 {len(all_results)} 個專利")
    
    # 保存搜索結果
    with open(os.path.join(OUTPUT_DIR, "patent_search_results.json"), "w") as f:
        json.dump({"results": all_results}, f, indent=2)
    
    # 階段 2: 提取
    print("階段 2: 提取專利詳情...")
    extracted = []
    for i, patent in enumerate(all_results[:TARGET_COUNT], 1):
        print(f"[{i}/{len(all_results)}] 提取：{patent['title'][:50]}...")
        try:
            result = app.scrape(url=patent["url"], formats=["markdown"])
            extracted.append({
                "url": patent["url"],
                "title": patent["title"],
                "content": result.markdown[:5000] if result.markdown else "",
                "success": True
            })
        except Exception as e:
            extracted.append({
                "url": patent["url"],
                "title": patent["title"],
                "content": "",
                "success": False,
                "error": str(e)
            })
    
    # 保存提取結果
    with open(os.path.join(OUTPUT_DIR, "extracted_patents_v2.json"), "w") as f:
        json.dump(extracted, f, indent=2)
    
    print(f"提取完成：{len([x for x in extracted if x['success']])}/{len(extracted)}")
    print("報告已生成")

if __name__ == "__main__":
    main()
