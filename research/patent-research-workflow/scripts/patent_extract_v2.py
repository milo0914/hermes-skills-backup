#!/usr/bin/env python3
"""
Merck KGaA 負介電液晶專利提取 (v2 - 改進版)
改進重點：
1. 優化的提取 prompt，明確要求提取 Claim 1 和實施例
2. 使用 Firecrawl scrape 提取完整頁面內容
3. 使用 LLM 分析並提取結構化數據
"""

from firecrawl import FirecrawlApp
import os
import json
import time
from datetime import datetime

# 檢查 API Key
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")
if not FIRECRAWL_API_KEY:
    print("❌ 錯誤：FIRECRAWL_API_KEY 未設置")
    exit(1)

app = FirecrawlApp(api_key=FIRECRAWL_API_KEY)

# 從之前的搜索結果加載專利 URL
search_file = "/tmp/patent_search_results.json"  # 使用舊的搜索結果
if not os.path.exists(search_file):
    print(f"❌ 錯誤：找不到搜索結果文件 {search_file}")
    exit(1)

with open(search_file, "r", encoding="utf-8") as f:
    search_data = json.load(f)

# 提取專利 URL (兼容舊格式)
patent_urls = []

# 格式 1: 新格式 (直接是 list)
if isinstance(search_data, list):
    for result in search_data:
        if isinstance(result, dict) and 'url' in result:
            patent_urls.append({
                "url": result.get('url', ''),
                "title": result.get('title', ''),
                "source_query": result.get('source_query', '')
            })
# 格式 2: 舊格式 (有 'results' key)
elif isinstance(search_data, dict):
    results = search_data.get('results', [])
    for result in results:
        if isinstance(result, dict) and 'url' in result:
            patent_urls.append({
                "url": result.get('url', ''),
                "title": result.get('title', ''),
                "source_query": result.get('source_query', '')
            })

print(f"從搜索結果中找到 {len(patent_urls)} 個專利")

print("=" * 80)
print("Merck KGaA 負介電液晶專利提取 (v2 - 改進版)")
print("=" * 80)
print(f"提取時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"目標專利數量：{len(patent_urls)}")
print("=" * 80)

# 定義提取 schema - 改進版，更明確要求 Claim 1 和實施例
extraction_schema = {
    "type": "object",
    "properties": {
        "patent_number": {
            "type": "string",
            "description": "專利號 (例如：US8399073B2, EP2031040A1)"
        },
        "filing_date": {
            "type": "string",
            "description": "申請日期 (YYYY-MM-DD)"
        },
        "publication_date": {
            "type": "string",
            "description": "公開日期 (YYYY-MM-DD)"
        },
        "title": {
            "type": "string",
            "description": "專利標題"
        },
        "assignee": {
            "type": "string",
            "description": "申請人/公司名稱"
        },
        "technical_features": {
            "type": "array",
            "items": {"type": "string"},
            "description": "技術特點列表（3-5 項）"
        },
        "claim_1": {
            "type": "string",
            "description": "Claim 1 完整內容（必須是 Claims 部分編號為 1 的完整條目，不能省略）"
        },
        "claims_count": {
            "type": "integer",
            "description": "申請專利範圍總數（如果有）"
        },
        "molecular_structure": {
            "type": "string",
            "description": "分子結構描述（如果有）"
        },
        "examples": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "example_number": {"type": "string"},
                    "content": {"type": "string"},
                    "effect": {"type": "string"}
                }
            },
            "description": "實施例列表（必須包含所有編號的實施例，每個實施例包含編號、內容摘要和效果）"
        },
        "cpc_codes": {
            "type": "array",
            "items": {"type": "string"},
            "description": "CPC 分類號列表"
        }
    },
    "required": ["patent_number", "title", "claim_1"]
}

# 優化的提取 prompt
extraction_prompt = """你是一位專利分析專家。請從這個專利頁面中提取以下信息：

重要要求：
1. **Claim 1**: 必須找到 "Claims" 部分，然後提取編號為 "1\" 的完整條目。不要省略任何內容。如果 Claim 1 有多個段落，請全部提取。
2. **實施例**: 找到所有 "Example" 或 "Embodiment" 編號的段落，提取每個實施例的完整內容摘要和效果。
3. **申請日期**: 找到 "filing date" 或 "申請日期" 字段，格式為 YYYY-MM-DD。
4. **專利號**: 提取完整的專利號碼。

如果任何字段不存在，請使用空字符串或空數組，不要編造數據。
只提取頁面中實際存在的內容。
"""

# 批量提取
extracted_patents = []
success_count = 0

for i, patent in enumerate(patent_urls, 1):
    print(f"\n[{i}/{len(patent_urls)}] 提取：{patent['title'][:60]}...")
    
    try:
        # 使用 LLM Extraction - 注意 urls 是複數形式
        extract_result = app.extract(
            urls=[patent['url']],
            schema=extraction_schema,
            prompt=extraction_prompt
        )
        
        # 提取結果結構：extract_result.data 包含提取的數據
        extracted_data = {}
        if hasattr(extract_result, 'data') and extract_result.data:
            extracted_data = extract_result.data
        elif isinstance(extract_result, dict) and 'data' in extract_result:
            extracted_data = extract_result['data']
        
        # 驗證提取結果
        if not extracted_data or not extracted_data.get("patent_number"):
            print(f"  ✗ 提取結果為空或缺少專利號")
            extracted_patents.append({
                "original": patent,
                "extracted": {},
                "error": "Empty extraction result or missing patent number"
            })
            continue
        
        # 添加專利連結
        extracted_data["patent_url"] = patent["url"]
        extracted_data["source_query"] = patent.get("source_query", "")
        
        extracted_patents.append({
            "original": patent,
            "extracted": extracted_data
        })
        success_count += 1
        
        # 打印摘要
        pat_num = extracted_data.get("patent_number", "N/A")
        title = extracted_data.get("title", "N/A")
        claim_1_len = len(extracted_data.get("claim_1", ""))
        examples_count = len(extracted_data.get("examples", []))
        
        print(f"  ✓ 提取成功")
        print(f"    專利號：{pat_num}")
        print(f"    標題：{title[:60]}...")
        print(f"    Claim 1 長度：{claim_1_len} 字元")
        print(f"    實施例數量：{examples_count}")
        
    except Exception as e:
        print(f"  ✗ 提取失敗：{e}")
        extracted_patents.append({
            "original": patent,
            "extracted": {},
            "error": str(e)
        })
    
    # 添加延遲避免請求過快
    time.sleep(3)

# 保存提取結果
extract_file = "/tmp/extracted_patents_v2.json"
with open(extract_file, "w", encoding="utf-8") as f:
    json.dump(extracted_patents, f, indent=2, ensure_ascii=False)

print(f"\n提取結果已保存：{extract_file}")
print(f"提取完成：成功 {success_count}/{len(patent_urls)}")

# 生成簡單的統計
print("\n" + "=" * 80)
print("提取統計")
print("=" * 80)

# 檢查 Claim 1 和實施例的完整性
claim_1_count = sum(1 for p in extracted_patents if p.get('extracted', {}).get('claim_1'))
examples_count = sum(len(p.get('extracted', {}).get('examples', [])) for p in extracted_patents if 'examples' in p.get('extracted', {}))

print(f"有 Claim 1 的專利：{claim_1_count}/{success_count}")
print(f"實施例總數：{examples_count}")

# 檢查日期範圍
date_range_check = []
for p in extracted_patents:
    filing_date = p.get('extracted', {}).get('filing_date', '')
    if filing_date:
        try:
            year = int(filing_date.split('-')[0])
            if 2020 <= year <= 2026:
                date_range_check.append(True)
            else:
                date_range_check.append(False)
        except:
            pass

if date_range_check:
    print(f"符合日期範圍 (2020-2026) 的專利：{sum(date_range_check)}/{len(date_range_check)}")

print("\n" + "=" * 80)
print("下一步：生成報告")
print("=" * 80)
