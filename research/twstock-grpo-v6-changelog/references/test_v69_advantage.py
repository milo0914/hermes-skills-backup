#!/usr/bin/env python3
"""
v6.9 Advantage Collapse 獨立驗證
比較 Rank-Based vs Z-score normalization 在各種情境下的表現
"""
import sys
sys.path.insert(0, '/home/appuser')

import numpy as np
from test_v69_advantage import test_rank_vs_zscore

if __name__ == "__main__":
    test_rank_vs_zscore()