#!/usr/bin/env python3
"""
Merck KGaA 負介電液晶專利搜索腳本 v5-TheLens 版
使用 The Lens 批量下載 + Python 過濾

優點：
- 無需 API key
- 無需 GCP 認證
- CSV 格式易於處理
- 完全免費

缺點：
- 需手動下載 CSV 文件
- 數據更新較慢（每月更新）
"""

import json
import os
import requests
import zipfile
from pathlib import Path

def download_lens_data(years=[2020, 2021, 2022, 2023, 2024, 2025, 2026]):
    """
    從 The Lens 下載美國授權專利 CSV
    """
    base_url = "https://bulk-data.lens.org/patent/us/granted/csv"
    download_dir = Path("/tmp/lens_patents")
    download_dir.mkdir(exist_ok=True)

    print("=" * 80)
    print("The Lens 批量下載")
    print("=" * 80)

    downloaded_files = []
    for year in years:
        filename = f"US_{year}_granted.zip"
        url = f"{base_url}/{filename}"
        output_path = download_dir / filename

        if output_path.exists():
            print(f"✓ 已存在：{output_path}")
            downloaded_files.append(output_path)
            continue

        print(f"下載中：{url}")
        try:
            response = requests.get(url, stream=True, timeout=300)
            if response.status_code == 200:
                with open(output_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                print(f"✓ 下載完成：{output_path}")
                downloaded_files.append(output_path)
            else:
                print(f"✗ 下載失敗：{response.status_code}")
        except Exception as e:
            print(f"✗ 錯誤：{e}")

    return downloaded_files


def filter_merck_patents(csv_files, output_file="/tmp/merck_patents_lens.json"):
    """
    從 CSV 文件中過濾 Merck KGaA 專利
    """
    import csv

    print("\n" + "=" * 80)
    print("過濾 Merck KGaA 專利")
    print("=" * 80)

    merck_patents = []
    keywords = ["merck", "emd", "negative dielectric", "liquid crystal"]
    cpc_keywords = ["C09K19/30", "C09K19/34", "C09K19/52"]

    for csv_file in csv_files:
        print(f"\n處理文件：{csv_file}")

        # 解壓縮 ZIP
        if csv_file.suffix == ".zip":
            with zipfile.ZipFile(csv_file, 'r') as zip_ref:
                zip_ref.extractall(csv_file.parent)
                csv_name = zip_ref.namelist()[0]
                csv_path = csv_file.parent / csv_name
        else:
            csv_path = csv_file

        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # 檢查申請人
                    applicant = row.get('applicant', '').lower()
                    title = row.get('title', '').lower()
                    abstract = row.get('abstract', '').lower()

                    # 檢查 CPC 分類
                    cpc = row.get('cpc', '').upper()

                    # 過濾條件
                    is_merck = any(kw in applicant for kw in ["merck", "emd"])
                    has_cpc = any(cpc_kw in cpc for cpc_kw in cpc_keywords)
                    has_keyword = any(kw in title or kw in abstract for kw in ["dielectric", "liquid crystal"])

                    if is_merck and (has_cpc or has_keyword):
                        patent = {
                            "publication_number": row.get('publication_number', ''),
                            "title": row.get('title', ''),
                            "abstract": row.get('abstract', ''),
                            "applicant": row.get('applicant', ''),
                            "filing_date": row.get('filing_date', ''),
                            "publication_date": row.get('publication_date', ''),
                            "cpc": row.get('cpc', ''),
                            "source": str(csv_file)
                        }
                        merck_patents.append(patent)
                        print(f"  找到：{patent['publication_number']} - {patent['title'][:50]}...")

        except Exception as e:
            print(f"處理文件時出錯：{e}")

    # 保存結果
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            "count": len(merck_patents),
            "patents": merck_patents
        }, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 80)
    print(f"過濾完成！共找到 {len(merck_patents)} 個 Merck KGaA 專利")
    print(f"結果已保存至：{output_file}")
    print("=" * 80)

    return merck_patents


if __name__ == "__main__":
    print("Merck KGaA 負介電液晶專利搜索 - The Lens 方案")
    print("說明：此腳本需要手動下載 CSV 文件，或使用下面的 URL 直接下載")
    print("=" * 80)

    # 提供下載連結列表
    print("\n請訪問以下連結下載 CSV 文件：")
    for year in [2020, 2021, 2022, 2023, 2024, 2025]:
        url = f"https://bulk-data.lens.org/patent/us/granted/csv/US_{year}_granted.zip"
        print(f"  {year}: {url}")

    print("\n下載後將 ZIP 文件放到 /tmp/lens_patents/ 目錄")
    print("然後執行：python patent_search_v5_lens.py")

    # 實際使用時執行：
    # files = download_lens_data()
    # patents = filter_merck_patents(files)
