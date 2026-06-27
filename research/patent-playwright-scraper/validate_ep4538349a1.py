#!/usr/bin/env python3
"""驗證 EP4538349A1 提取 + 技術要點生成完整流程"""
import sys, json, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))
from tech_feature_generator import extract_patent_sections, build_tech_feature_prompt

url = "https://patents.google.com/patent/EP4538349A1/en"

print("=" * 60)
print(f"提取: {url}")
print("=" * 60)

result = extract_patent_sections(url)

# 輸出提取摘要
summary = {
    'patent_number': result.get('patent_number', ''),
    'title': result.get('title', ''),
    'abstract_len': len(result.get('abstract', '')),
    'claim_1_len': len(result.get('claim_1', '')),
    'claim_2_len': len(result.get('claim_2', '')),
    'claim_3_len': len(result.get('claim_3', '')),
    'background_len': len(result.get('background', '')),
    'summary_len': len(result.get('summary', '')),
    'examples_count': result.get('examples_count', 0),
    'description_len': len(result.get('description', '')),
    'neg_count': result.get('negative_dielectric_count', 0),
    'pos_count': result.get('positive_dielectric_count', 0),
    'is_negative_da': result.get('is_negative_da', None),
}

print(json.dumps(summary, ensure_ascii=False, indent=2))

# 輸出關鍵段落預覽
if result.get('claim_1'):
    print(f"\n--- Claim 1 preview ({len(result['claim_1'])} chars) ---")
    print(result['claim_1'][:300])

if result.get('background'):
    print(f"\n--- Background preview ({len(result['background'])} chars) ---")
    print(result['background'][:300])

if result.get('summary'):
    print(f"\n--- Summary preview ({len(result['summary'])} chars) ---")
    print(result['summary'][:300])

# neg/pos 判定
print(f"\n--- 負介電判定 ---")
print(f"neg_count={summary['neg_count']}, pos_count={summary['pos_count']}, is_negative_da={summary['is_negative_da']}")

# 階段 4-5: 組裝技術要點 Prompt
print("\n" + "=" * 60)
print("組裝技術要點 Prompt")
print("=" * 60)

prompt = build_tech_feature_prompt(result)
if prompt:
    print(f"Prompt 長度: {len(prompt)} chars")
    # 保存 prompt 供後續 delegate_task 使用
    prompt_file = os.path.join(os.path.dirname(__file__), 'reports', 'ep4538349a1_prompt.json')
    os.makedirs(os.path.dirname(prompt_file), exist_ok=True)
    with open(prompt_file, 'w', encoding='utf-8') as f:
        json.dump({'patent_id': 'EP4538349A1', 'prompt': prompt, 'sections_summary': summary}, f, ensure_ascii=False, indent=2)
    print(f"Prompt 已保存: {prompt_file}")
else:
    print("⚠️ Prompt 生成失敗")

# 保存完整結果
output_file = os.path.join(os.path.dirname(__file__), 'reports', 'ep4538349a1_validation.json')
os.makedirs(os.path.dirname(output_file), exist_ok=True)
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
print(f"\n完整結果已保存: {output_file}")
