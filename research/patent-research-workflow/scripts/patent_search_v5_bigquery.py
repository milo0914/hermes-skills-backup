#!/usr/bin/env python3
"""
Merck KGaA 負介電液晶專利搜索腳本 v5
使用 Google Patents BigQuery API

目標：搜索 2020-2026 年間 Merck KGaA 的負介電液晶專利
"""

import json
from google.cloud import bigquery

def search_merck_patents():
    """
    使用 Google Patents BigQuery 搜索 Merck KGaA 負介電液晶專利
    """
    # 初始化 BigQuery 客戶端
    # 需要先設置環境變量：GOOGLE_APPLICATION_CREDENTIALS
    client = bigquery.Client()

    # SQL 查詢：Merck KGaA 2020-2026 負介電液晶專利
    query = """
    SELECT
      publication_number,
      title,
      abstract,
      filing_date,
      publication_date,
      applicant,
      ARRAY_AGG(cpc_codes.code) as cpc_codes
    FROM
      `patents-public-data.patents.publications`,
      UNNEST(cpc) AS cpc_codes
    WHERE
      (
        LOWER(applicant) LIKE '%merck%'
        OR LOWER(applicant) LIKE '%emd%'
      )
      AND filing_date BETWEEN DATE '2020-01-01' AND DATE '2026-12-31'
      AND (
        cpc_codes.code LIKE 'C09K19/30%' OR  -- 負介電各向異性
        cpc_codes.code LIKE 'C09K19/34%' OR  -- 液晶組合物
        cpc_codes.code LIKE 'C09K19/52%'     -- 液晶材料
      )
    GROUP BY
      publication_number, title, abstract, filing_date, publication_date, applicant
    ORDER BY
      filing_date DESC
    LIMIT 50
    """

    print("=" * 80)
    print("Merck KGaA 負介電液晶專利搜索 (Google Patents BigQuery)")
    print("=" * 80)
    print(f"查詢 SQL:\n{query}\n")
    print("=" * 80)

    try:
        # 執行查詢
        query_job = client.query(query)
        results = query_job.result()

        patents = []
        for row in results:
            patent = {
                "publication_number": row.publication_number,
                "title": row.title,
                "abstract": row.abstract,
                "filing_date": str(row.filing_date) if row.filing_date else None,
                "publication_date": str(row.publiculation_date) if row.publication_date else None,
                "applicant": row.applicant,
                "cpc_codes": list(row.cpc_codes) if row.cpc_codes else []
            }
            patents.append(patent)
            print(f"\n[{len(patents)}] {patent['publication_number']}")
            print(f"    標題：{patent['title'][:100]}...")
            print(f"    申請日：{patent['filing_date']}")
            print(f"    申請人：{patent['applicant']}")
            print(f"    CPC: {', '.join(patent['cpc_codes'][:3])}")

        # 保存結果
        output_file = "/tmp/patent_search_bigquery.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump({
                "query": query,
                "count": len(patents),
                "patents": patents
            }, f, ensure_ascii=False, indent=2)

        print("\n" + "=" * 80)
        print(f"搜索完成！共找到 {len(patents)} 個專利")
        print(f"結果已保存至：{output_file}")
        print("=" * 80)

        return patents

    except Exception as e:
        print(f"搜索失敗：{e}")
        print("\n可能原因:")
        print("1. 未設置 GOOGLE_APPLICATION_CREDENTIALS 環境變量")
        print("2. 未安裝 google-cloud-bigquery 庫")
        print("3. 網絡問題無法連接 BigQuery")
        print("\n解決方法:")
        print("1. 安裝依賴：pip install google-cloud-bigquery")
        print("2. 設置認證：export GOOGLE_APPLICATION_CREDENTIALS='/path/to/credentials.json'")
        print("3. 或使用替代方案：The Lens 批量下載")
        return []


def search_with_lens():
    """
    使用 The Lens 批量下載方案（備選方案）
    下載 2020-2026 年美國專利 CSV，然後用 Python 過濾
    """
    import requests
    import zipfile
    import os

    print("\n" + "=" * 80)
    print("The Lens 批量下載方案（備選）")
    print("=" * 80)

    base_url = "https://bulk-data.lens.org/patent/us/granted/csv/"
    years = range(2020, 2027)

    for year in years:
        url = f"{base_url}US_{year}_granted.zip"
        print(f"準備下載：{url}")
        # 實際使用時需要下載並解壓縮
        # 此處僅展示邏輯

    print("\nThe Lens 方案需要手動下載 CSV 文件並用 Python pandas 過濾")
    print("適合不需要實時數據的場景")


if __name__ == "__main__":
    # 首選方案：Google Patents BigQuery
    patents = search_merck_patents()

    if not patents:
        print("\nBigQuery 搜索失敗，考慮使用備選方案...")
        search_with_lens()
