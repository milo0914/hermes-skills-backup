"""
台股 AI Dig Money — 過擬合防護模組 (Anti-Overfitting Layer)

整合五層過擬合防護：
1. 資料分割 (Train/Val/Test)
2. Walk-Forward 驗證
3. GRPO 獎勵過擬合懲罰
4. 因子穩定性檢驗
5. Purged K-Fold 交叉驗證

參考：
- de Prado "Advances in Financial Machine Learning" Ch.7 (Cross-Validation)
- Bailey et al. "The Probability of Backtest Overfitting"
- White "Reality Check for Data Snooping"
"""
import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field
from enum import Enum


# ============================================================
# 1. 資料分割
# ============================================================

@dataclass
class DataSplit:
    """時間序列資料分割"""
    train_start: str
    train_end: str
    val_start: str
    val_end: str
    test_start: str
    test_end: str  # locked, never used in development


class TimeSeriesSplitter:
    """時間序列分割器 — 避免 look-ahead bias"""

    # 預設分割（台股 2023-2026）
    DEFAULT_SPLIT = DataSplit(
        train_start="2023-01-01", train_end="2024-06-30",
        val_start="2024-07-01", val_end="2024-12-31",
        test_start="2025-01-01", test_end="2025-12-31",
    )

    def __init__(self, split: DataSplit = None):
        self.split = split or self.DEFAULT_SPLIT

    def split_df(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """按日期分割 DataFrame"""
        df = df.copy()
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])

        train = df[(df["date"] >= self.split.train_start) &
                   (df["date"] <= self.split.train_end)]
        val = df[(df["date"] >= self.split.val_start) &
                 (df["date"] <= self.split.val_end)]
        test = df[(df["date"] >= self.split.test_start) &
                  (df["date"] <= self.split.test_end)]

        return train, val, test

    def assert_test_locked(self, used_dates: List[str]) -> bool:
        """確認 test 期間未被使用（開發過程中）"""
        test_start = pd.Timestamp(self.split.test_start)
        test_end = pd.Timestamp(self.split.test_end)
        for d in used_dates:
            ts = pd.Timestamp(d)
            if test_start <= ts <= test_end:
                return False
        return True


# ============================================================
# 2. Walk-Forward 驗證
# ============================================================

@dataclass
class WalkForwardResult:
    """單一 walk-forward 窗口結果"""
    window_id: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    train_sharpe: float
    oos_sharpe: float
    train_ic: float
    oos_ic: float
    overfit_ratio: float  # train_sharpe / oos_sharpe — > 2.0 過擬合

    @property
    def is_overfit(self) -> bool:
        return self.overfit_ratio > 2.0 or self.oos_sharpe < 0.5


class WalkForwardValidator:
    """
    滾動式 Walk-Forward 驗證

    - Window: train_months + test_months, 滾動 step_months
    - 至少 N 個 OOS 窗口
    - OOS Sharpe > 0.5 才接受
    """

    def __init__(self, train_months: int = 6, test_months: int = 1,
                 step_months: int = 1, min_windows: int = 6,
                 min_oos_sharpe: float = 0.5):
        self.train_months = train_months
        self.test_months = test_months
        self.step_months = step_months
        self.min_windows = min_windows
        self.min_oos_sharpe = min_oos_sharpe

    def generate_windows(self, start_date: str, end_date: str) -> List[Dict]:
        """生成 walk-forward 窗口"""
        start = pd.Timestamp(start_date)
        end = pd.Timestamp(end_date)
        windows = []
        current = start

        while True:
            train_end = current + pd.DateOffset(months=self.train_months)
            test_start = train_end + pd.DateOffset(days=1)
            test_end = test_start + pd.DateOffset(months=self.test_months)

            if test_end > end:
                break

            windows.append({
                "train_start": current.strftime("%Y-%m-%d"),
                "train_end": train_end.strftime("%Y-%m-%d"),
                "test_start": test_start.strftime("%Y-%m-%d"),
                "test_end": test_end.strftime("%Y-%m-%d"),
            })

            current += pd.DateOffset(months=self.step_months)

        return windows

    def evaluate(self, df: pd.DataFrame, strategy_fn, metric_fn) -> List[WalkForwardResult]:
        """
        執行 walk-forward 驗證

        Args:
            df: 完整歷史資料
            strategy_fn: function(train_df) -> strategy_params
            metric_fn: function(df, strategy_params) -> (sharpe, ic)

        Returns:
            每個窗口的 WalkForwardResult
        """
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])

        date_range = f"{df['date'].min().strftime('%Y-%m-%d')}" \
                     f"_{df['date'].max().strftime('%Y-%m-%d')}"
        windows = self.generate_windows(
            df["date"].min().strftime("%Y-%m-%d"),
            df["date"].max().strftime("%Y-%m-%d"),
        )

        results = []
        for i, w in enumerate(windows):
            train_df = df[(df["date"] >= w["train_start"]) &
                          (df["date"] <= w["train_end"])]
            test_df = df[(df["date"] >= w["test_start"]) &
                         (df["date"] <= w["test_end"])]

            if len(train_df) < 60 or len(test_df) < 5:
                continue

            # Train
            params = strategy_fn(train_df)
            train_sharpe, train_ic = metric_fn(train_df, params)
            oos_sharpe, oos_ic = metric_fn(test_df, params)

            overfit_ratio = abs(train_sharpe / (oos_sharpe + 1e-6))

            results.append(WalkForwardResult(
                window_id=i,
                train_start=w["train_start"],
                train_end=w["train_end"],
                test_start=w["test_start"],
                test_end=w["test_end"],
                train_sharpe=train_sharpe,
                oos_sharpe=oos_sharpe,
                train_ic=train_ic,
                oos_ic=oos_ic,
                overfit_ratio=overfit_ratio,
            ))

        return results

    def summarize(self, results: List[WalkForwardResult]) -> dict:
        """彙總 walk-forward 結果"""
        if not results:
            return {"status": "insufficient_data", "n_windows": 0}

        oos_sharpes = [r.oos_sharpe for r in results]
        overfit_ratios = [r.overfit_ratio for r in results]
        n_overfit = sum(1 for r in results if r.is_overfit)

        return {
            "n_windows": len(results),
            "min_oos_sharpe": min(oos_sharpes),
            "mean_oos_sharpe": np.mean(oos_sharpes),
            "median_oos_sharpe": np.median(oos_sharpes),
            "mean_overfit_ratio": np.mean(overfit_ratios),
            "n_overfit_windows": n_overfit,
            "overfit_rate": n_overfit / len(results),
            "pass": (len(results) >= self.min_windows and
                     np.median(oos_sharpes) >= self.min_oos_sharpe),
        }


# ============================================================
# 3. GRPO 獎勵過擬合懲罰
# ============================================================

class OverfitPenalty:
    """GRPO 獎勵函數中的過擬合懲罰項"""

    def __init__(self, ic_gap_threshold: float = 0.05,
                 turnover_max: float = 0.3,
                 ic_gap_weight: float = 2.0,
                 turnover_weight: float = 0.5):
        self.ic_gap_threshold = ic_gap_threshold
        self.turnover_max = turnover_max
        self.ic_gap_weight = ic_gap_weight
        self.turnover_weight = turnover_weight

    def compute(self, train_sharpe: float, val_sharpe: float,
                train_ic: float, val_ic: float,
                daily_turnover: float = 0.0) -> Dict[str, float]:
        """
        計算過擬合懲罰

        Returns:
            dict with base_reward, penalties, final_reward
        """
        base_reward = train_sharpe

        # IC 衰減懲罰：train IC 遠高於 val IC → 過擬合
        ic_gap = max(0, train_ic - val_ic - self.ic_gap_threshold)
        ic_penalty = self.ic_gap_weight * ic_gap

        # 換手率懲罰：過度交易
        turnover_penalty = self.turnover_weight * max(0, daily_turnover - self.turnover_max)

        # 夏普衰減懲罰：train sharpe 遠高於 val sharpe
        sharpe_decay = max(0, train_sharpe - val_sharpe * 2.0) / (train_sharpe + 1e-6)

        total_penalty = ic_penalty + turnover_penalty + sharpe_decay
        final_reward = base_reward - total_penalty

        return {
            "base_reward": base_reward,
            "ic_penalty": ic_penalty,
            "turnover_penalty": turnover_penalty,
            "sharpe_decay_penalty": sharpe_decay,
            "total_penalty": total_penalty,
            "final_reward": final_reward,
            "is_overfit": ic_gap > 0.1 or sharpe_decay > 0.3,
        }


# ============================================================
# 4. 因子穩定性檢驗
# ============================================================

class FactorStabilityChecker:
    """因子穩定性檢驗 — IC 衰減、換手率、多空對稱性"""

    def __init__(self, ic_window: int = 60, ic_decay_threshold: float = 0.3,
                 turnover_max: float = 0.3, symmetry_max_ratio: float = 2.0):
        self.ic_window = ic_window
        self.ic_decay_threshold = ic_decay_threshold
        self.turnover_max = turnover_max
        self.symmetry_max_ratio = symmetry_max_ratio

    def compute_ic(self, factor_values: pd.Series,
                   forward_returns: pd.Series) -> float:
        """計算 Rank IC (Spearman 相關係數)"""
        valid = factor_values.notna() & forward_returns.notna()
        if valid.sum() < 10:
            return 0.0
        return factor_values[valid].corr(forward_returns[valid], method="spearman")

    def rolling_ic(self, factor_values: pd.Series,
                   forward_returns: pd.Series,
                   date_series: pd.Series) -> pd.Series:
        """滾動 IC 時間序列"""
        ic_series = []
        dates = []

        for i in range(self.ic_window, len(factor_values)):
            f_window = factor_values.iloc[i - self.ic_window:i]
            r_window = forward_returns.iloc[i - self.ic_window:i]
            ic = f_window.corr(r_window, method="spearman")
            ic_series.append(ic)
            dates.append(date_series.iloc[i])

        return pd.Series(ic_series, index=dates)

    def check_ic_decay(self, factor_values: pd.Series,
                       forward_returns: pd.Series,
                       date_series: pd.Series) -> dict:
        """IC 衰減測試：最近 3 個月的 IC 是否顯著下降"""
        df_temp = pd.DataFrame({
            "factor": factor_values,
            "fwd_ret": forward_returns,
            "date": date_series,
        }).dropna()

        if len(df_temp) < 60:
            return {"status": "insufficient_data", "ic_decay": 0.0}

        # 全期 IC
        full_ic = df_temp["factor"].corr(df_temp["fwd_ret"], method="spearman")

        # 最近 3 個月 IC
        latest_date = df_temp["date"].max()
        recent_cutoff = latest_date - pd.DateOffset(months=3)
        recent = df_temp[df_temp["date"] >= recent_cutoff]
        recent_ic = recent["factor"].corr(recent["fwd_ret"], method="spearman") \
            if len(recent) >= 20 else 0.0

        decay = full_ic - recent_ic
        is_decaying = decay > self.ic_decay_threshold * abs(full_ic)

        return {
            "full_ic": full_ic,
            "recent_ic": recent_ic,
            "ic_decay": decay,
            "is_decaying": is_decaying,
            "warning": f"IC 衰減 {decay:.3f}，因子可能失效" if is_decaying else "",
        }

    def check_turnover(self, factor_values: pd.Series) -> dict:
        """換手率檢驗"""
        if len(factor_values) < 2:
            return {"daily_turnover": 0.0, "is_excessive": False}

        # 排名變化率作為換手率代理
        ranks = factor_values.rank(pct=True)
        rank_changes = ranks.diff().abs()
        daily_turnover = rank_changes.mean()

        return {
            "daily_turnover": daily_turnover,
            "is_excessive": daily_turnover > self.turnover_max,
        }

    def check_long_short_symmetry(self, factor_values: pd.Series,
                                  forward_returns: pd.Series) -> dict:
        """多空對稱性檢驗"""
        df_temp = pd.DataFrame({
            "factor": factor_values,
            "fwd_ret": forward_returns,
        }).dropna()

        if len(df_temp) < 30:
            return {"symmetry_ratio": 1.0, "is_asymmetric": False}

        median = df_temp["factor"].median()
        long_ret = df_temp[df_temp["factor"] > median]["fwd_ret"].mean()
        short_ret = df_temp[df_temp["factor"] <= median]["fwd_ret"].mean()

        if abs(short_ret) < 1e-8:
            ratio = float("inf") if abs(long_ret) > 1e-8 else 1.0
        else:
            ratio = abs(long_ret / short_ret)

        return {
            "long_return": long_ret,
            "short_return": short_ret,
            "symmetry_ratio": ratio,
            "is_asymmetric": ratio > self.symmetry_max_ratio,
        }

    def full_check(self, factor_values: pd.Series,
                   forward_returns: pd.Series,
                   date_series: pd.Series = None) -> dict:
        """完整因子穩定性檢驗"""
        if date_series is None and hasattr(factor_values, "index"):
            date_series = pd.Series(factor_values.index)

        results = {
            "ic_decay": self.check_ic_decay(factor_values, forward_returns,
                                            date_series),
            "turnover": self.check_turnover(factor_values),
            "symmetry": self.check_long_short_symmetry(factor_values,
                                                       forward_returns),
        }

        # 綜合判斷
        issues = []
        if results["ic_decay"].get("is_decaying"):
            issues.append("IC 衰減")
        if results["turnover"].get("is_excessive"):
            issues.append("換手率過高")
        if results["symmetry"].get("is_asymmetric"):
            issues.append("多空不對稱")

        results["is_stable"] = len(issues) == 0
        results["issues"] = issues
        return results


# ============================================================
# 5. Purged K-Fold 交叉驗證
# ============================================================

class PurgedKFold:
    """
    Purged K-Fold 交叉驗證 (de Prado, AFML Ch.7)

    在 fold 邊界加入 embargo 期間，消除自相關造成的 look-ahead bias。
    適用於時間序列策略回測。
    """

    def __init__(self, n_splits: int = 5, embargo_days: int = 7,
                 sharpe_std_threshold: float = 0.3):
        self.n_splits = n_splits
        self.embargo_days = embargo_days
        self.sharpe_std_threshold = sharpe_std_threshold

    def split(self, dates: pd.DatetimeIndex) -> List[Tuple[np.ndarray, np.ndarray]]:
        """
        生成 purged train/test index 分割

        Args:
            dates: 日期索引

        Returns:
            List of (train_idx, test_idx) tuples
        """
        n = len(dates)
        fold_size = n // self.n_splits
        splits = []

        for i in range(self.n_splits):
            test_start = i * fold_size
            test_end = (i + 1) * fold_size if i < self.n_splits - 1 else n

            # Embargo: test 期間前後各 embargo_days 天從 train 中移除
            embargo_start = max(0, test_start - self.embargo_days)
            embargo_end = min(n, test_end + self.embargo_days)

            train_idx = np.concatenate([
                np.arange(0, embargo_start),
                np.arange(embargo_end, n),
            ]).astype(int)
            test_idx = np.arange(test_start, test_end).astype(int)

            # 移除超出範圍的
            train_idx = train_idx[(train_idx >= 0) & (train_idx < n)]
            test_idx = test_idx[(test_idx >= 0) & (test_idx < n)]

            if len(train_idx) > 0 and len(test_idx) > 0:
                splits.append((train_idx, test_idx))

        return splits

    def cross_validate(self, df: pd.DataFrame, strategy_fn,
                       metric_fn) -> dict:
        """
        執行 Purged K-Fold 交叉驗證

        Args:
            df: 完整資料（需含 date 欄位）
            strategy_fn: function(train_df) -> params
            metric_fn: function(df, params) -> sharpe

        Returns:
            彙總結果
        """
        if "date" in df.columns:
            df = df.copy()
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date").reset_index(drop=True)

        dates = pd.DatetimeIndex(df["date"])
        splits = self.split(dates)

        fold_sharpes = []
        for fold_id, (train_idx, test_idx) in enumerate(splits):
            train_df = df.iloc[train_idx]
            test_df = df.iloc[test_idx]

            if len(train_df) < 60 or len(test_df) < 5:
                continue

            params = strategy_fn(train_df)
            train_sharpe = metric_fn(train_df, params)
            test_sharpe = metric_fn(test_df, params)

            fold_sharpes.append({
                "fold": fold_id,
                "train_sharpe": train_sharpe,
                "test_sharpe": test_sharpe,
                "sharpe_gap": train_sharpe - test_sharpe,
            })

        if not fold_sharpes:
            return {"status": "insufficient_data", "n_folds": 0}

        test_sharpes = [f["test_sharpe"] for f in fold_sharpes]
        sharpe_std = np.std(test_sharpes)

        return {
            "n_folds": len(fold_sharpes),
            "folds": fold_sharpes,
            "mean_test_sharpe": np.mean(test_sharpes),
            "std_test_sharpe": sharpe_std,
            "is_overfit": sharpe_std > self.sharpe_std_threshold,
            "warning": f"Fold 間夏普標準差 {sharpe_std:.3f} > " \
                       f"{self.sharpe_std_threshold} → 過擬合風險" \
                if sharpe_std > self.sharpe_std_threshold else "",
        }


# ============================================================
# 6. 綜合過擬合報告
# ============================================================

@dataclass
class OverfitReport:
    """過擬合綜合報告"""
    strategy_name: str
    walk_forward: Optional[dict] = None
    factor_stability: Optional[dict] = None
    purged_kfold: Optional[dict] = None
    is_safe: bool = False
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "strategy_name": self.strategy_name,
            "is_safe": self.is_safe,
            "warnings": self.warnings,
            "walk_forward": self.walk_forward,
            "factor_stability": self.factor_stability,
            "purged_kfold": self.purged_kfold,
        }


class AntiOverfitLayer:
    """
    過擬合防護層 — 統一入口

    用法：
        layer = AntiOverfitLayer()
        report = layer.full_audit(df, strategy_fn, metric_fn, factor_series, fwd_ret_series)
        if not report.is_safe:
            print("過擬合警告:", report.warnings)
    """

    def __init__(self, config: dict = None):
        config = config or {}
        self.splitter = TimeSeriesSplitter(
            DataSplit(**config.get("data_split", {}))
            if "data_split" in config else None
        )
        self.wf_validator = WalkForwardValidator(
            **config.get("walk_forward", {})
        )
        self.penalty = OverfitPenalty(
            **config.get("penalty", {})
        )
        self.stability = FactorStabilityChecker(
            **config.get("stability", {})
        )
        self.purged_kfold = PurgedKFold(
            **config.get("purged_kfold", {})
        )

    def full_audit(self, df: pd.DataFrame, strategy_fn, metric_fn,
                   factor_values: pd.Series = None,
                   forward_returns: pd.Series = None,
                   date_series: pd.Series = None,
                   name: str = "unnamed") -> OverfitReport:
        """完整過擬合審計"""
        report = OverfitReport(strategy_name=name)
        warnings = []

        # 1. Walk-Forward
        try:
            wf_results = self.wf_validator.evaluate(df, strategy_fn, metric_fn)
            wf_summary = self.wf_validator.summarize(wf_results)
            report.walk_forward = wf_summary
            if not wf_summary.get("pass", False):
                warnings.append(
                    f"Walk-Forward 未通過: 中位數 OOS Sharpe "
                    f"{wf_summary.get('median_oos_sharpe', 0):.2f}"
                )
        except Exception as e:
            warnings.append(f"Walk-Forward 執行失敗: {e}")
            report.walk_forward = {"error": str(e)}

        # 2. 因子穩定性
        if factor_values is not None and forward_returns is not None:
            try:
                stability = self.stability.full_check(
                    factor_values, forward_returns, date_series
                )
                report.factor_stability = stability
                if not stability.get("is_stable", True):
                    warnings.append(
                        f"因子不穩定: {', '.join(stability.get('issues', []))}"
                    )
            except Exception as e:
                warnings.append(f"因子穩定性檢驗失敗: {e}")

        # 3. Purged K-Fold
        try:
            kfold_result = self.purged_kfold.cross_validate(df, strategy_fn, metric_fn)
            report.purged_kfold = kfold_result
            if kfold_result.get("is_overfit", False):
                warnings.append(kfold_result.get("warning", "Purged K-Fold 過擬合"))
        except Exception as e:
            warnings.append(f"Purged K-Fold 執行失敗: {e}")
            report.purged_kfold = {"error": str(e)}

        # 綜合判斷
        report.warnings = warnings
        report.is_safe = len(warnings) == 0

        return report

    def grpo_reward_with_penalty(self, train_sharpe: float, val_sharpe: float,
                                 train_ic: float, val_ic: float,
                                 daily_turnover: float = 0.0) -> dict:
        """GRPO 獎勵 + 過擬合懲罰（用於訓練迴圈）"""
        return self.penalty.compute(
            train_sharpe, val_sharpe, train_ic, val_ic, daily_turnover
        )


# ============================================================
# 使用範例
# ============================================================

def demo():
    """示範過擬合防護模組"""
    print("=" * 50)
    print("過擬合防護模組 — 示範")
    print("=" * 50)

    # 1. 資料分割
    splitter = TimeSeriesSplitter()
    train, val, test = splitter.split_df(pd.DataFrame())  # 需真實資料
    print(f"Train: {splitter.split.train_start} ~ {splitter.split.train_end}")
    print(f"Val:   {splitter.split.val_start} ~ {splitter.split.val_end}")
    print(f"Test:  {splitter.split.test_start} ~ {splitter.split.test_end} (LOCKED)")

    # 2. Walk-Forward 窗口
    wf = WalkForwardValidator(train_months=6, test_months=1)
    windows = wf.generate_windows("2023-01-01", "2025-12-31")
    print(f"\nWalk-Forward: {len(windows)} 個窗口")
    for w in windows[:3]:
        print(f"  Train: {w['train_start']}~{w['train_end']} "
              f"Test: {w['test_start']}~{w['test_end']}")

    # 3. 過擬合懲罰
    penalty = OverfitPenalty()
    result = penalty.compute(train_sharpe=2.0, val_sharpe=0.8,
                             train_ic=0.15, val_ic=0.05)
    print(f"\n過擬合懲罰範例:")
    print(f"  Base reward: {result['base_reward']:.2f}")
    print(f"  IC penalty:  {result['ic_penalty']:.2f}")
    print(f"  Final:       {result['final_reward']:.2f}")
    print(f"  Is overfit:  {result['is_overfit']}")

    # 4. Purged K-Fold
    pkf = PurgedKFold(n_splits=5, embargo_days=7)
    dates = pd.bdate_range("2023-01-01", "2025-12-31")
    splits = pkf.split(dates)
    print(f"\nPurged K-Fold: {len(splits)} folds, "
          f"embargo={pkf.embargo_days} days")

    print("\n[OK] 過擬合防護模組就緒")


if __name__ == "__main__":
    demo()
