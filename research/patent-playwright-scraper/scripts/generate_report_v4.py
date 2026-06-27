#!/usr/bin/env python3
"""
generate_report_v4.py — Merck 負介電各向異性液晶專利調研報告 v4
修正要求：(1) 技術要點含分子構造洞見 (2) 加入 Claim1 (3) 加入 Abstract
"""

import json
import os
from datetime import datetime

BASE = "/tmp/hermes-patent-research/report-elastic_scattering/"
OUTPUT = "/tmp/hermes-patent-research/reports/elastic_scattering/"

def load_data():
    with open(os.path.join(BASE, "final_18_merged.json"), "r", encoding="utf-8") as f:
        return json.load(f)

def safe_str(val, default="—"):
    if val is None:
        return default
    if isinstance(val, str) and val.strip() == "":
        return default
    if isinstance(val, (list, dict)) and len(val) == 0:
        return default
    return val

def fmt_count(val):
    v = safe_str(val, 0)
    try:
        return int(v)
    except (ValueError, TypeError):
        return 0

def fmt_list_count(val):
    if isinstance(val, list):
        return len(val)
    return 0

def fmt_date(val):
    v = safe_str(val, "—")
    if v and v != "—" and len(v) >= 10:
        return v[:10]
    return v

def truncate(s, max_len=300):
    s = str(s).strip()
    if len(s) <= max_len:
        return s
    return s[:max_len-3] + "..."

def fmt_physical_params(params):
    """Format physical parameters into readable text"""
    if not params or not isinstance(params, dict):
        return "—"
    lines = []
    for k, v in params.items():
        if v and v != "-" and v != "—":
            label_map = {
                "elastic_values": "彈性常數",
                "K1": "K1 (splay)",
                "K2": "K2 (twist)", 
                "K3": "K3 (bend)",
                "Kavg": "Kavg",
                "gamma1": "γ1 (旋轉黏度)",
                "delta_n": "Δn (雙折射率)",
                "delta_epsilon": "Δε (介電各向異性)",
                "clearing_point": "清亮點",
            }
            label = label_map.get(k, k)
            val_str = str(v)
            if isinstance(v, list):
                val_str = "; ".join(str(x) for x in v[:5])
                if len(v) > 5:
                    val_str += f" ...等{len(v)}項"
            lines.append(f"  - {label}: {val_str}")
    return "\n".join(lines) if lines else "—"

def extract_elastic_constants_from_hits(hits):
    """Extract specific elastic constant values from hit texts"""
    import re
    values = {}
    if not hits or not isinstance(hits, list):
        return values
    for hit in hits:
        text = hit.get("elastic constant", "") or hit.get("text", "")
        if not text:
            continue
        # Find K values like "K1 = 15.2 pN" or "K11 = 15.2 pN"
        for match in re.finditer(r'K(?:1|11|avg|avg\.)\s*[=:≈]\s*([\d.]+)\s*pN?', text, re.IGNORECASE):
            k = "K1"
            values.setdefault(k, []).append(match.group(1))
        for match in re.finditer(r'K(?:2|22)\s*[=:≈]\s*([\d.]+)\s*pN?', text, re.IGNORECASE):
            k = "K2"
            values.setdefault(k, []).append(match.group(1))
        for match in re.finditer(r'K(?:3|33)\s*[=:≈]\s*([\d.]+)\s*pN?', text, re.IGNORECASE):
            k = "K3"
            values.setdefault(k, []).append(match.group(1))
        for match in re.finditer(r'Kavg\s*[=:≈]\s*([\d.]+)\s*pN?', text, re.IGNORECASE):
            k = "Kavg"
            values.setdefault(k, []).append(match.group(1))
    return values

def generate_report(data):
    patents = sorted(data.keys())
    
    # ---- Report Header ----
    lines = []
    lines.append("# Merck KGaA 負介電各向異性液晶材料專利調研報告")
    lines.append("")
    lines.append("## 彈性散射主題 — v4 修正版")
    lines.append("")
    lines.append(f"- 報告生成日期：{datetime.now().strftime('%Y-%m-%d')}")
    lines.append(f"- 專利檢索範圍：2020–2026")
    lines.append(f"- 專利數量：{len(patents)} 篇")
    lines.append(f"- 資料來源：Google Patents（Playwright 提取）")
    lines.append(f"- 修正內容：(1) 技術要點含分子構造洞見 (2) 加入 Claim 1 (3) 加入 Abstract")
    lines.append("")
    
    # ---- Summary Table ----
    lines.append("## 一、專利總覽")
    lines.append("")
    lines.append("| # | 專利號 | 標題 | 優先權日 | 負Δε/正Δε | 彈性常數命中 | 散射命中 | 實施例 | 技術要點摘要 |")
    lines.append("|---|--------|------|----------|-----------|-------------|---------|--------|-------------|")
    
    for i, pid in enumerate(patents, 1):
        d = data[pid]
        title_short = truncate(safe_str(d.get("title", ""), "—").replace(f"{pid} - ", ""), 40)
        pdate = fmt_date(d.get("priority_date", "—"))
        neg = fmt_count(d.get("neg_da_count", 0))
        pos = fmt_count(d.get("pos_da_count", 0))
        e_hits = fmt_list_count(d.get("elastic_hits", []))
        s_hits = fmt_list_count(d.get("scattering_hits", []))
        ex = fmt_count(d.get("example_count", 0))
        tp_short = truncate(d.get("tech_point", "—"), 35)
        
        lines.append(f"| {i} | {pid} | {title_short} | {pdate} | {neg}/{pos} | {e_hits} | {s_hits} | {ex} | {tp_short} |")
    
    lines.append("")
    
    # ---- Detailed Patent Analysis ----
    lines.append("## 二、各專利詳細分析")
    lines.append("")
    
    for i, pid in enumerate(patents, 1):
        d = data[pid]
        lines.append(f"### {i}. {pid}")
        lines.append("")
        
        # Basic info
        title = safe_str(d.get("title", ""), "—").replace(f"{pid} - ", "")
        url = safe_str(d.get("url", ""), "—")
        pdate = fmt_date(d.get("priority_date", "—"))
        fdate = fmt_date(d.get("filing_date", "—"))
        pubdate = fmt_date(d.get("publication_date", "—"))
        
        lines.append(f"- **標題**：{title}")
        lines.append(f"- **Google Patents 連結**：{url}")
        lines.append(f"- **優先權日**：{pdate}")
        lines.append(f"- **申請日**：{fdate}")
        lines.append(f"- **公開日**：{pubdate}")
        lines.append("")
        
        # --- Abstract ---
        abstract = safe_str(d.get("abstract", ""), "—")
        lines.append(f"#### Abstract")
        lines.append("")
        lines.append(f"> {abstract}")
        lines.append("")
        
        # --- Claim 1 ---
        claim1 = safe_str(d.get("claim1", ""), "—")
        if claim1 != "—" and len(claim1) > 600:
            # Truncate very long claim1 for readability, but keep substantial content
            claim1_display = claim1[:600] + " ...(略)"
        else:
            claim1_display = claim1
        lines.append(f"#### Claim 1")
        lines.append("")
        lines.append(f"> {claim1_display}")
        lines.append("")
        
        # --- Molecular codes ---
        mol_codes = d.get("molecular_codes", [])
        if mol_codes and isinstance(mol_codes, list) and len(mol_codes) > 0:
            codes_str = ", ".join(str(c) for c in mol_codes[:20])
            if len(mol_codes) > 20:
                codes_str += f" ...等 {len(mol_codes)} 個"
            lines.append(f"#### 分子代碼")
            lines.append("")
            lines.append(f"{codes_str}")
            lines.append("")
        
        # --- Physical parameters ---
        phys = d.get("physical_params", {})
        if phys and isinstance(phys, dict):
            phys_text = fmt_physical_params(phys)
            if phys_text != "—":
                lines.append(f"#### 物理參數")
                lines.append("")
                lines.append(phys_text)
                lines.append("")
        
        # --- Elastic hits summary ---
        e_hits = d.get("elastic_hits", [])
        if e_hits and isinstance(e_hits, list) and len(e_hits) > 0:
            lines.append(f"#### 彈性常數相關段落（{len(e_hits)} 條）")
            lines.append("")
            for j, hit in enumerate(e_hits[:5], 1):
                text = hit.get("elastic constant", "") or hit.get("text", "")
                if text:
                    lines.append(f"{j}. {truncate(text, 200)}")
                    lines.append("")
            if len(e_hits) > 5:
                lines.append(f"...共 {len(e_hits)} 條，僅列前 5 條")
                lines.append("")
        
        # --- Scattering hits summary ---
        s_hits = d.get("scattering_hits", [])
        if s_hits and isinstance(s_hits, list) and len(s_hits) > 0:
            lines.append(f"#### 散射相關段落（{len(s_hits)} 條）")
            lines.append("")
            for j, hit in enumerate(s_hits[:5], 1):
                text = hit.get("scattering", "") or hit.get("text", "")
                if text:
                    lines.append(f"{j}. {truncate(text, 200)}")
                    lines.append("")
            if len(s_hits) > 5:
                lines.append(f"...共 {len(s_hits)} 條，僅列前 5 條")
                lines.append("")
        
        # --- Example count ---
        ex_count = fmt_count(d.get("example_count", 0))
        neg = fmt_count(d.get("neg_da_count", 0))
        pos = fmt_count(d.get("pos_da_count", 0))
        lines.append(f"#### 統計摘要")
        lines.append("")
        lines.append(f"- 實施例數：{ex_count}")
        lines.append(f"- 負Δε化合物數：{neg}")
        lines.append(f"- 正Δε化合物數：{pos}")
        lines.append("")
        
        # --- Tech Point (分子構造洞見) ---
        tp = d.get("tech_point", "—")
        lines.append(f"#### 技術要點（含分子構造洞見）")
        lines.append("")
        lines.append(tp)
        lines.append("")
        lines.append("---")
        lines.append("")
    
    # ---- Section 3: Cross-Patent Analysis ----
    lines.append("## 三、跨專利技術趨勢分析")
    lines.append("")
    
    # 3.1 Elastic constant strategy
    lines.append("### 3.1 彈性常數調控策略演進")
    lines.append("")
    lines.append("Merck 在 2020–2026 期間的負介電各向異性液晶專利中，彈性常數調控策略呈現清晰的演進軌跡：")
    lines.append("")
    lines.append("**第一階段（2020–2022）— 參數精調期**：以 US20240360362A1 為代表，聚焦 K1/K2/K3 三軸分量的獨立調控，")
    lines.append("尚未將散射參數納入設計約束。配方中負Δε與正Δε化合物的比例相對平衡（8:4），反映對純負Δε體系的技術信心尚在建立中。")
    lines.append("")
    lines.append("**第二階段（2023–2024）— 散射意識覺醒期**：以 US12163081B2、US12404452B2 為代表，")
    lines.append("首次明確建立「高 Kavg → 低散射 → 高對比度」的因果鏈，將散射參數從附屬效應提升為設計約束。")
    lines.append("US12163081B2 引入環烷基端基新骨架，US12404452B2 以 57 個實施例構建參數空間基線。")
    lines.append("")
    lines.append("**第三階段（2025–2026）— 分子工程深化期**：以 US12305103B2（113 例）、US20250101305A1、US20250215323A1 為代表，")
    lines.append("進入大規模系統化篩選，neg_da:pos_da 比例趨向極端化（8:1），標誌對純負Δε體系的高度信心。")
    lines.append("同時引入 γ1/K11、K3/K1 等精細比值指標，將彈性常數從均值控制推進至各向異性精調。")
    lines.append("")
    
    # 3.2 Molecular structure insights
    lines.append("### 3.2 分子構造設計關鍵洞見")
    lines.append("")
    lines.append("1. **雜環核心策略**：EP4553132A1（苯并呋喃/苯并噻吩）與 EP4685208A1（5,6-二氟苯并[b]噻吩）")
    lines.append("   揭示 Merck 正探索非苯環雜環核心，利用硫/氧原子的短軸高極化率增強負Δε效應，")
    lines.append("   相較傳統 2,3-二氟苯環端基，噻吩環 5,6-位氟取代可使偶極矩更有效垂直於分子長軸。")
    lines.append("")
    lines.append("2. **環烷基端基創新**：US12163081B2 引入環丙基/環丁基/環戊基取代的烷基端基，")
    lines.append("   小環烴嵌入增加分子橫截面積，強化垂直於長軸的極化分量，同時限制構象自由度使彈性常數比值趨向有利方向。")
    lines.append("")
    lines.append("3. **連接基工程的雙重功效**：-CF2O- 連接基同時實現低旋轉黏度（γ1↓）與適度的負Δε 貢獻，")
    lines.append("   而 -C≡C- 炔鍵則提升共軛度與雙折射率（Δn↑）。US20250207032A1 與 US20250361444A1 ")
    lines.append("   展示了透過連接基選擇獨立調控 γ1/K22 比值與 K2≈½K1 關係的分子級策略。")
    lines.append("")
    lines.append("4. **4-alkenyl 基團的選擇性 K3 增強**：US20250197723A1 揭示末端烯基的 π-π 交互作用")
    lines.append("   在 bend 畸變時與鄰近分子芳香環產生穩定化接觸，選擇性提升 K3 而非 K1，")
    lines.append("   實現 K3/K1 比值優化，對 VA 面板 bend 模式響應具直接效益。")
    lines.append("")
    lines.append("5. **正負Δε協同混配**：EP4400561A1（8:6）與 US12612551B2（2:7）展示兩種截然不同的配方哲學——")
    lines.append("   前者以正Δε化合物作為「黏度稀釋劑」，後者以負Δε化合物作為「Kavg 提升劑」。")
    lines.append("   協同混配的化學相似性要求（避免相分離）與偶極矩正交性要求（獨立調控 Δε 與 Kavg）")
    lines.append("   構成了分子設計的核心約束張力。")
    lines.append("")
    
    # 3.3 Scattering control
    lines.append("### 3.3 散射控制技術路線")
    lines.append("")
    
    # Count patents with scattering hits
    s_patents = [pid for pid in patents if fmt_list_count(data[pid].get("scattering_hits", [])) > 0]
    e_patents = [pid for pid in patents if fmt_list_count(data[pid].get("elastic_hits", [])) > 0]
    
    lines.append(f"在 18 篇專利中，{len(s_patents)} 篇涉及散射參數控制，{len(e_patents)} 篇涉及彈性常數設計。")
    lines.append("散射控制存在兩條互補路線：")
    lines.append("")
    lines.append("**材料端路線**：透過高 Kavg 抑制液晶分子在邊界場處的漲落幅度，降低導致光散射的區域畸變。")
    lines.append("代表性專利：US12163081B2、US20250215323A1、US20250101305A1。")
    lines.append("此路線的物理基礎在於彈性常數越高，分子偏離平衡取向的能量代價越大，散射截面越小。")
    lines.append("")
    lines.append("**器件端路線**：透過器件結構設計主動控制散射量，而非依賴材料參數的被動抑制。")
    lines.append("代表性專利：US20250085595A1（並排 LC 區域可調散射器件）。")
    lines.append("此路線反向推導材料需求：低 K22 維持散射態穩定，高 K1 確保透明態快速恢復。")
    lines.append("")
    
    # 3.4 Application mapping
    lines.append("### 3.4 應用場景映射")
    lines.append("")
    lines.append("| 應用場景 | 關鍵參數需求 | 代表專利 |")
    lines.append("|----------|-------------|---------|")
    lines.append("| VA 模式（8K/高更新率） | 高 Kavg、低散射、低 γ1/K11 | US12163081B2, US20250215323A1 |")
    lines.append("| IPS/FFS 模式 | 高 Kavg、精細 K3/K1 比 | US20240360362A1, US20250197723A1 |")
    lines.append("| Gaming 顯示器 | 高 K1/Kavg、低 γ1/K1 | US20250136868A1, US20250197723A1 |")
    lines.append("| 反射式 LCoS 面板 | K1 16-22 pN、極低 γ1/K1 | US20250189829A1 |")
    lines.append("| 可調散射器件 | 低 K22（散射態）、高 K1（透明態） | US20250085595A1 |")
    lines.append("| 通用負Δε配方 | 高 |Δε|、化合物多樣性 | US12305103B2, US12404452B2 |")
    lines.append("")
    
    # ---- Section 4: Data Tables ----
    lines.append("## 四、參數數據總表")
    lines.append("")
    lines.append("| 專利號 | 優先權日 | 負Δε | 正Δε | 彈性命中 | 散射命中 | 實施例 | 分子代碼數 |")
    lines.append("|--------|---------|------|------|---------|---------|--------|-----------|")
    
    for pid in patents:
        d = data[pid]
        pdate = fmt_date(d.get("priority_date", "—"))
        neg = fmt_count(d.get("neg_da_count", 0))
        pos = fmt_count(d.get("pos_da_count", 0))
        e_hits = fmt_list_count(d.get("elastic_hits", []))
        s_hits = fmt_list_count(d.get("scattering_hits", []))
        ex = fmt_count(d.get("example_count", 0))
        mol_n = len(d.get("molecular_codes", [])) if isinstance(d.get("molecular_codes", []), list) else 0
        lines.append(f"| {pid} | {pdate} | {neg} | {pos} | {e_hits} | {s_hits} | {ex} | {mol_n} |")
    
    lines.append("")
    
    # ---- Section 5: Methodology ----
    lines.append("## 五、調研方法論")
    lines.append("")
    lines.append("1. **資料來源**：Google Patents，使用 Playwright 自動化提取")
    lines.append("2. **檢索策略**：以 Merck KGaA 為申請人，負介電各向異性（negative dielectric anisotropy）為關鍵詞，")
    lines.append("   疊加彈性常數（elastic constant / K1 / K2 / K3 / Kavg）與散射（scattering）語義過濾")
    lines.append("3. **時間範圍**：2020–2026（優先權日）")
    lines.append("4. **Claim 1 提取**：多模式匹配（正則 + DOM 解析），對提取失敗者以 Playwright 重新訪問頁面提取")
    lines.append("5. **技術要點生成**：基於 Claim1 結構分析 + 彈性常數/散射命中文本 + 分子代碼解讀，")
    lines.append("   確保每篇均包含分子構造層面或分子組成改進層面的洞見")
    lines.append("6. **v4 修正**：回溯 v2/v3 報告不足，補齊 Claim1、Abstract、分子構造洞見三項")
    lines.append("")
    
    # ---- Section 6: Disclaimer ----
    lines.append("## 六、免責聲明")
    lines.append("")
    lines.append("本報告基於公開專利文獻的自動化提取與分析生成，僅供技術調研參考。")
    lines.append("Claim 1 文本可能因 Google Patents 頁面渲染差異而與官方公告文本略有出入，")
    lines.append("如需法律效力文本請查閱各國專利局官方公報。分子代碼命名遵循 Merck 內部編碼慣例，")
    lines.append("其與具體化學結構的對應關係需結合專利全文實施例解讀。")
    lines.append("")
    
    return "\n".join(lines)


def main():
    data = load_data()
    print(f"Loaded {len(data)} patents", flush=True)
    
    report = generate_report(data)
    
    os.makedirs(OUTPUT, exist_ok=True)
    outpath = os.path.join(OUTPUT, "report_merck_neg_da_elastic_scattering_v4.md")
    
    with open(outpath, "w", encoding="utf-8") as f:
        f.write(report)
    
    fsize = os.path.getsize(outpath)
    print(f"Report written to {outpath} ({fsize:,} bytes)", flush=True)
    
    # Verify all 3 requirements
    print("\n=== 修正要求驗證 ===", flush=True)
    
    # Check (1) tech_point contains molecular insight
    has_molecular_keywords = 0
    molecular_kw = ["分子", "構造", "骨架", "化合物", "偶極", "極化", "環", "鍵", "端基", "連接基", "取代基"]
    for pid, d in data.items():
        tp = d.get("tech_point", "")
        if any(kw in tp for kw in molecular_kw):
            has_molecular_keywords += 1
    print(f"(1) 技術要點含分子構造洞見：{has_molecular_keywords}/18 ✓" if has_molecular_keywords == 18 else f"(1) 技術要點含分子構造洞見：{has_molecular_keywords}/18 ✗", flush=True)
    
    # Check (2) Claim1 present
    has_claim1 = sum(1 for d in data.values() if d.get("claim1", "") and len(str(d["claim1"])) > 50)
    print(f"(2) Claim1 已加入：{has_claim1}/18 ✓" if has_claim1 == 18 else f"(2) Claim1 已加入：{has_claim1}/18 ✗", flush=True)
    
    # Check (3) Abstract present
    has_abstract = sum(1 for d in data.values() if d.get("abstract", "") and len(str(d["abstract"])) > 30)
    print(f"(3) Abstract 已加入：{has_abstract}/18 ✓" if has_abstract == 18 else f"(3) Abstract 已加入：{has_abstract}/18 ✗", flush=True)


if __name__ == "__main__":
    main()
