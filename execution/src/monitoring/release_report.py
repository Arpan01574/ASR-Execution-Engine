import logging
from typing import Dict
from datetime import datetime

logger = logging.getLogger(__name__)

def generate_release_readiness_report(
    backtest_metrics: dict,
    paper_metrics: dict,
    demo_metrics: dict,
    system_checks: dict
) -> str:
    """
    Evaluates all metrics and system checks to determine the final release candidate status,
    as required by Prompt 5 (25. FINAL RELEASE REPORT).
    """
    
    # 1. Evaluate Sample Sizes
    n_bt = backtest_metrics.get("trade_count", 0)
    n_paper = paper_metrics.get("trade_count", 0)
    n_demo = demo_metrics.get("trade_count", 0)
    
    # Predefined thresholds
    REQ_BT = 300
    REQ_PAPER = 100
    REQ_DEMO = 100
    
    # 2. Evaluate System Checks
    parity_pass = system_checks.get("parity_pass", False)
    reconciliation_pass = system_checks.get("reconciliation_pass", False)
    lookahead_free = system_checks.get("lookahead_free", True)
    
    # 3. Determine Status
    status = "NOT READY"
    reasons = []
    
    if not lookahead_free:
        reasons.append("Lookahead bias detected or unverified.")
    if not parity_pass:
        reasons.append("Pine/Python Parity test failed.")
    if n_bt < REQ_BT:
        reasons.append(f"Insufficient Backtest Trades ({n_bt} < {REQ_BT}).")
        
    if not reasons:
        status = "RESEARCH READY"
        
        if n_paper >= REQ_PAPER:
            status = "PAPER READY"
            
            if reconciliation_pass and n_demo >= REQ_DEMO:
                status = "DEMO READY"
                
                # Live requires explicit manual verification
                if system_checks.get("live_confirm_flag", False):
                    status = "LIVE CANDIDATE"
                else:
                    reasons.append("LIVE_CONFIRM flag not set by operator.")
            else:
                if not reconciliation_pass:
                    reasons.append("Reconciliation checks failed in Paper/Demo.")
                if n_demo < REQ_DEMO:
                    reasons.append(f"Insufficient Demo Trades ({n_demo} < {REQ_DEMO}).")
    
    # Format Report
    report = []
    report.append("==================================================")
    report.append("  ASR Engine v3 — RELEASE READINESS REPORT")
    report.append("==================================================")
    report.append(f"Date generated: {datetime.now().isoformat()}\n")
    
    report.append(f"FINAL CLASSIFICATION: [{status}]\n")
    
    report.append("1. STRATEGY & BACKTEST QUALITY")
    report.append(f"  - No-Lookahead Verified : {lookahead_free}")
    report.append(f"  - Pine/Python Parity    : {parity_pass}")
    report.append(f"  - Backtest Trade Count  : {n_bt} (Req: {REQ_BT})")
    report.append(f"  - Backtest Expectancy   : {backtest_metrics.get('expectancy_R', 0):.2f} R\n")
    
    report.append("2. EXECUTION QUALITY (PAPER & DEMO)")
    report.append(f"  - Paper Trade Count     : {n_paper} (Req: {REQ_PAPER})")
    report.append(f"  - Demo Trade Count      : {n_demo} (Req: {REQ_DEMO})")
    report.append(f"  - Reconciliation Pass   : {reconciliation_pass}\n")
    
    if reasons:
        report.append("3. BLOCKERS TO NEXT STAGE")
        for r in reasons:
            report.append(f"  - {r}")
            
    report.append("\n==================================================")
    
    return "\n".join(report)
