# v13 Offline Test Results — 18 Merck KGaA Patents

**Date**: 2026-06-04
**Script**: `scripts/patent_extract_v13_refined.py` (1,367 lines)
**Test Data**: `/tmp/hermes-patent-research-fresh/report-elastic_scattering/final_18_merged.json`

## Summary

| Metric | v4 Baseline | v11 | v13 |
|--------|------------|-----|-----|
| Δε misclassifications | 3/18 (16.7%) | 3/18 (16.7%)* | 0/18 (0%) |
| AMBIGUOUS | N/A | 4/18 | 5/18 |
| Example coverage | 3/18 (17%) | 3/18 (17%) | 3/18 + tail scans |
| Description truncation | 16/18 (89%) | 16/18 (89%) | 16/18 (89%) |

*v11 had the three-tier evidence hierarchy in code but the v4 data was generated before v11 existed.

## Δε Classification Results (v13 Four-Layer Classifier)

| Patent | Layer | Result | Confidence | Source |
|--------|-------|--------|------------|--------|
| EP4400561A1 | 1 | NEG | 0.95 | abstract: "negative dielectric anisotropy" |
| EP4553132A1 | — | AMBIGUOUS | 0.00 | microwave/high-freq app, no DA sign in abstract |
| EP4680691A1 | 4b | NEG | 0.70 | "instead of positive" in description |
| EP4685208A1 | 1 | POS | 0.95 | abstract: "positive dielectric anisotropy" |
| US12163081B2 | 1 | NEG | 0.95 | abstract: "negative dielectric anisotropy" |
| US12305103B2 | 1 | NEG | 0.95 | abstract: "negative dielectric anisotropy" |
| US12404452B2 | 1 | NEG | 0.95 | abstract: "negative dielectric anisotropy" |
| US12612551B2 | 1 | POS | 0.95 | abstract: "positive dielectric anisotropy" (was wrong: NEG) |
| US20240360362A1 | 1 | NEG | 0.95 | abstract: "negative dielectric anisotropy" |
| US20250085595A1 | — | AMBIGUOUS | 0.00 | optical scattering device, LC is peripheral |
| US20250101305A1 | 1 | NEG | 0.95 | abstract: "negative dielectric anisotropy" |
| US20250136868A1 | 1 | POS | 0.95 | abstract: "positive VA" |
| US20250189829A1 | 1 | NEG | 0.95 | abstract: "negative dielectric anisotropy" |
| US20250197723A1 | 1 | POS | 0.95 | abstract: "positive VA or positive PS-VA" |
| US20250207032A1 | 1 | POS | 0.95 | abstract: "positive dielectric anisotropy" (was wrong: NEG) |
| US20250215323A1 | 1 | NEG | 0.95 | abstract: "negative dielectric anisotropy" |
| US20250284151A1 | 1 | NEG | 0.95 | abstract: "negative dielectric anisotropy" |
| US20250361444A1 | 1 | POS | 0.95 | abstract: "positive dielectric anisotropy" (was wrong: NEG) |

## Corrected Patients (3 Misclassifications Fixed)

| Patent | v4/v11 Wrong | v13 Correct | Key Evidence |
|--------|-------------|------------|-------------|
| US12612551B2 | is_negative_da=True | POS | abstract explicitly says "positive dielectric anisotropy" |
| US20250207032A1 | is_negative_da=True | POS | abstract explicitly says "positive dielectric anisotropy" |
| US20250361444A1 | is_negative_da=True | POS | abstract explicitly says "positive dielectric anisotropy" |

## AMBIGUOUS Patents (5)

| Patent | Reason | Action |
|--------|--------|--------|
| EP4553132A1 | Microwave/high-freq application; abstract says "dielectric anisotropy" without sign | Legitimate AMBIGUOUS — may need full-text extraction |
| US20250085595A1 | Optical scattering device; LC medium is peripheral component | Legitimate AMBIGUOUS — DA sign is not the invention's focus |
| 3 truncated patents | Description truncated at 50k/80k, no tail evidence available | Need full-text Playwright extraction to re-classify |

## Key Findings

1. **Abstract is the strongest single evidence source**: 13/18 patents classified at Layer 1 (confidence 0.95)
2. **"instead of" pattern works**: EP4680691A1 matched at Layer 4b with confidence 0.70
3. **Display mode ≠ DA sign**: EP4400561A1 is FFS + negative DA; US20250136868A1 is VA + positive DA
4. **Description counting is unreliable**: Prior art mentions both signs, making simple counts misleading
5. **Truncation remains the #1 blocker for examples**: 83% of patents lose their example sections due to 50k/80k char limits

## Next Steps

1. Full-text Playwright extraction for the 3 truncated AMBIGUOUS patents
2. Re-run Δε classification with full description available
3. Validate example extraction on full-text data
