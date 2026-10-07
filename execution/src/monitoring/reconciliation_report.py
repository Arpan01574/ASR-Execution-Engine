import logging
from typing import Dict, List
import pandas as pd
from datetime import datetime

logger = logging.getLogger(__name__)

class ExecutionReconciliationReport:
    """
    Compares Backtest Expectancy vs Paper vs Demo execution.
    Flags divergences per Prompt 5 requirements.
    """
    
    def __init__(self, tolerances: dict = None):
        # Predefined tolerances as demanded by Prompt 5
        self.tolerances = tolerances or {
            "slippage_r_max": 0.1,    # Max allowed slippage in R
            "win_rate_delta": 5.0,    # Max % difference in win rate
            "expectancy_delta": 0.1,  # Max R difference in expectancy
            "latency_ms_max": 200     # Max acceptable latency
        }
        
    def generate_report(self, backtest_stats: dict, live_stats: dict, environment: str = "DEMO") -> str:
        """
        Compares live/paper execution metrics against canonical backtest metrics.
        """
        bt_wr = backtest_stats.get("win_rate_%", 0)
        live_wr = live_stats.get("win_rate_%", 0)
        wr_delta = abs(bt_wr - live_wr)
        
        bt_exp = backtest_stats.get("expectancy_R", 0)
        live_exp = live_stats.get("expectancy_R", 0)
        exp_delta = abs(bt_exp - live_exp)
        
        avg_slippage_r = live_stats.get("avg_slippage_R", 0)
        avg_latency_ms = live_stats.get("avg_latency_ms", 0)
        
        # Color Coding / Flagging
        flags = []
        if wr_delta > self.tolerances["win_rate_delta"]:
            flags.append(f"🔴 RED: Win rate divergence ({wr_delta:.1f}%) > {self.tolerances['win_rate_delta']}%")
        else:
            flags.append(f"🟢 GREEN: Win rate aligned (delta {wr_delta:.1f}%)")
            
        if exp_delta > self.tolerances["expectancy_delta"]:
            flags.append(f"🔴 RED: Expectancy divergence ({exp_delta:.2f}R) > {self.tolerances['expectancy_delta']}R")
        else:
            flags.append(f"🟢 GREEN: Expectancy aligned (delta {exp_delta:.2f}R)")
            
        if avg_slippage_r > self.tolerances["slippage_r_max"]:
            flags.append(f"🔴 RED: High Slippage ({avg_slippage_r:.2f}R) > {self.tolerances['slippage_r_max']}R")
        else:
            flags.append(f"🟢 GREEN: Acceptable Slippage ({avg_slippage_r:.2f}R)")
            
        if avg_latency_ms > self.tolerances["latency_ms_max"]:
            flags.append(f"🟡 YELLOW: High Latency ({avg_latency_ms:.0f}ms) > {self.tolerances['latency_ms_max']}ms")
            
        # Format output
        report = []
        report.append(f"=== ASR Engine v3 | Execution vs Backtest Reconciliation ({environment}) ===")
        report.append(f"Timestamp: {datetime.now().isoformat()}")
        report.append("-" * 60)
        report.append(f"{'Metric':<20} | {'Backtest':<10} | {'Live/Demo':<10} | {'Delta'}")
        report.append("-" * 60)
        report.append(f"{'Win Rate (%)':<20} | {bt_wr:<10.1f} | {live_wr:<10.1f} | {wr_delta:.1f}%")
        report.append(f"{'Expectancy (R)':<20} | {bt_exp:<10.2f} | {live_exp:<10.2f} | {exp_delta:.2f}R")
        report.append(f"{'Profit Factor':<20} | {backtest_stats.get('profit_factor',0):<10.2f} | {live_stats.get('profit_factor',0):<10.2f} | -")
        report.append("-" * 60)
        report.append(f"Avg Slippage (R) : {avg_slippage_r:.3f}")
        report.append(f"Avg Latency (ms) : {avg_latency_ms:.0f}")
        report.append("-" * 60)
        report.append("STATUS FLAGS:")
        for flag in flags:
            report.append("  " + flag)
            
        return "\n".join(report)
