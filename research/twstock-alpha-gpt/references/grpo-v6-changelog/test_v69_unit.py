#!/usr/bin/env python3
"""
v6.9 核心邏輯單元測試
測試 Rank-Based Advantage、Multi-Objective Reward、Dynamic Group Size
"""
import sys
sys.path.insert(0, '/home/appuser')

import numpy as np
import torch
from test_v69_core import test_advantage_and_reward

if __name__ == "__main__":
    test_advantage_and_reward()