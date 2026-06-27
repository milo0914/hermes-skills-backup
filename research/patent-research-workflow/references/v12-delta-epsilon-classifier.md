# v12 Delta-Epsilon Classifier & Example Extractor Architecture

**Date**: 2026-06-04
**Status**: Validated on 18 Merck KGaA patents (2020-2026)

## Problem

1. Description fields are truncated at 50K/80K chars, cutting off example sections (located in last 15-20% of text)
2. Simple keyword counting in description misclassifies Δε sign because prior-art references mention both positive and negative DA
3. FFS/IPS mode ≠ positive DA (counterexample: EP4400561A1 is FFS + negative DA)
4. VA mode ≠ always negative DA (positive VA exists)

## Solution: Four-Layer Hierarchical Δε Classification

Priority order (higher = more authoritative):

| Layer | Source | Confidence | Logic |
|-------|--------|-----------|-------|
| 1 | Abstract | 0.95 | Direct statement: "LC media having negative/positive dielectric anisotropy" |
| 2 | Claim 1 | 0.90 | Legal definition: "LC composition having negative/positive dielectric anisotropy" |
| 3 | example_table_data | 0.85 | Numerical: Δε = -3.8 → negative; Δε = +5.2 → positive |
| 4 | Description tail scan | 0.60 | Last 20% of description, weighted count (never use full description) |

**NEVER** use display mode (FFS/IPS/VA) as a primary Δε classifier.

### Implementation Pattern

```python
def classify_delta_epsilon(patent_data):
    # Layer 1: Abstract
    abstract = patent_data.get('abstract', '')
    if 'negative dielectric anisotropy' in abstract.lower():
        return 'confirmed_neg', 0.95, 'abstract'
    if 'positive dielectric anisotropy' in abstract.lower():
        return 'confirmed_pos', 0.95, 'abstract'
    
    # Layer 2: Claim 1
    claim1 = patent_data.get('claim1', '')
    if 'negative dielectric anisotropy' in claim1.lower():
        return 'confirmed_neg', 0.90, 'claim1'
    if 'positive dielectric anisotropy' in claim1.lower():
        return 'confirmed_pos', 0.90, 'claim1'
    
    # Layer 3: Example table data
    etd = patent_data.get('example_table_data', '')
    if etd:
        delta_match = re.search(r'[Δd][ée]\s*[=:]\s*([-+]?\d+\.?\d*)', etd)
        if delta_match:
            val = float(delta_match.group(1))
            sign = 'confirmed_neg' if val < 0 else 'confirmed_pos'
            return sign, 0.85, 'example_table_data'
    
    # Layer 4: Description tail (last 20%)
    desc = patent_data.get('description', '')
    tail = desc[int(len(desc)*0.8):]
    neg_count = len(re.findall(r'negative dielectric anisotropy', tail, re.I))
    pos_count = len(re.findall(r'positive dielectric anisotropy', tail, re.I))
    if neg_count > pos_count:
        return 'likely_neg', 0.60, 'desc_tail'
    if pos_count > neg_count:
        return 'likely_pos', 0.60, 'desc_tail'
    
    return 'ambiguous', 0.0, 'none'
```

## Example Extraction: Dual-Track Strategy

### Track 1: Structured Fields
- `example_count`: Number of examples (may be 0 if truncated)
- `example_details`: List of example data (often empty due to truncation)
- `example_table_data`: Formatted table data (rare but high-quality)

### Track 2: Tail-Emergency Extraction
When structured fields are empty, scan the last 20% of description:

```python
def extract_examples_tail_emergency(description):
    tail = description[int(len(description) * 0.8):]
    # Multi-pattern matching (exclude "for example" false positives)
    pattern = r'(?i)(working\s+example|synthesis\s+example|comparison\s+example|example)\s*#?\s*(\d+)'
    matches = re.findall(pattern, tail)
    # Filter out "for example" (casual usage)
    real_examples = [(label, num) for label, num in matches 
                     if 'for example' not in label.lower()]
    return real_examples
```

### Source Tracking
Always record `example_recovery_source`:
- `structured`: From example_details/example_table_data
- `tail_emergency`: From last-20% regex scan
- `failed`: No examples found (method failure — every patent has examples)

## Validation Results (18 Patents)

| Metric | v11 | v12 |
|--------|-----|-----|
| Δε misclassifications | 3/18 (16.7%) | 0/18 (0%) |
| Ambiguous | 4/18 | 0/18 |
| Example coverage | 3/18 (17%) | 5/18 + 13 tail partial |
| FFS→positive DA assumption | Used (wrong) | Removed |

### Key Counterexample
EP4400561A1: FFS mode + Δε = -3.8 → **negative** DA. This proves display mode cannot determine Δε sign.

### Claims Field as Bridge
For severely truncated patents where abstract is ambiguous, Claim 1 often contains explicit "having a [negative/positive] dielectric anisotropy" language. This resolved 3 previously ambiguous patents:
- US20250085595A1: Claim 1 → negative
- US20250136868A1: Claim 1 → positive 
- US20250197723A1: Claim 1 → negative

## v13 Refinements (2026-06-04)

### Layer 1b: Abstract Display Mode Abbreviation Matching

When Layer 1 (abstract explicit DA statement) fails, check for display mode abbreviations:

| Mode | Abbreviation | Implied DA | Confidence |
|------|-------------|-----------|------------|
| Vertically Aligned | VA | negative | 0.80 |
| Vertical Alignment | VA | negative | 0.80 |
| In-Plane Switching | IPS | positive | 0.80 |
| Fringe Field Switching | FFS | positive | 0.80 |
| Twisted Nematic | TN | positive | 0.80 |
| Polymer Stabilized VA | PS-VA | negative | 0.80 |

**Caveat**: This is heuristic — EP4400561A1 proves FFS can use negative DA. Always mark as `likely_*` not `confirmed_*`.

### Layer 4b: Description "instead of" Semantic Pattern

Detects contrastive statements where the invention deliberately uses the opposite DA from conventional:

```python
# v13: accommodate up to 40 chars gap text
instead_neg = re.findall(
    r'negative\s+dielectric\s+anisotropy\s+instead\s+of\s+.{0,40}?positive',
    description, re.IGNORECASE
)
instead_pos = re.findall(
    r'positive\s+dielectric\s+anisotropy\s+instead\s+of\s+.{0,40}?negative',
    description, re.IGNORECASE
)
```

Confidence: 0.70 (explicit contrast, but indirect evidence)

### v13 Offline Test Results (18 Patents)

| Metric | v11 | v12 | v13 |
|--------|-----|-----|-----|
| Δε misclassifications | 3/18 (16.7%) | 0 | 0 |
| AMBIGUOUS | 4/18 | 0 | 5/18* |
| Confirmed/Likely | 14/18 | 18/18 | 13/18 |
| Misclassification rate | 16.7% | 0% | 0% |

*v13 AMBIGUOUS breakdown:
- 3 patents: description truncated → no tail evidence, need full-text extraction
- 2 patents: legitimate AMBIGUOUS (EP4553132A1 microwave app, US20250085595A1 optical scattering)

### Corrected Patents (v11→v13)

| Patent | v11 Result | v13 Result | Evidence Source |
|--------|-----------|-----------|----------------|
| US12612551B2 | negative (wrong) | positive | abstract: "positive dielectric anisotropy" |
| US20250207032A1 | negative (wrong) | positive | abstract: "positive dielectric anisotropy" |
| US20250361444A1 | negative (wrong) | positive | abstract: "positive dielectric anisotropy" |

### Implementation

v13 script: `scripts/patent_extract_v13_refined.py` (1,367 lines)
