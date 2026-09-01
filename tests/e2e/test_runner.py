#!/usr/bin/env python3
"""
NFL +EV Betting Application — Standalone E2E Test Suite Runner

CLI executable for running Tiers 1 through 4 with options for tier filtering,
verbose logging, structured JSON reports, fail-fast execution, and pattern filtering.
"""

import sys
import os
import time
import json
import argparse
import unittest
import traceback
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Import tier test modules
from tests.e2e.tier1_feature_coverage import TestTier1FeatureCoverage
from tests.e2e.tier2_boundary_corner import TestTier2BoundaryCorner
from tests.e2e.tier3_pairwise_combinations import TestTier3PairwiseCombinations
from tests.e2e.tier4_real_world_workloads import TestTier4RealWorldWorkloads


class TerminalColor:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    GREEN = "\033[32m"
    RED = "\033[31m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    @classmethod
    def enable_colors(cls, mode: str) -> bool:
        if mode == "never":
            return False
        if mode == "always":
            return True
        # auto
        if "NO_COLOR" in os.environ:
            return False
        return sys.stdout.isatty() or os.name == "nt"


class CustomTestResult(unittest.TestResult):
    def __init__(self, verbose: bool = False, fail_fast: bool = False, use_color: bool = True):
        super().__init__()
        self.verbose = verbose
        self.fail_fast = fail_fast
        self.use_color = use_color
        self.test_records: List[Dict[str, Any]] = []
        self._current_test_start = 0.0

    def _format(self, text: str, color_code: str) -> str:
        if not self.use_color:
            return text
        return f"{color_code}{text}{TerminalColor.RESET}"

    def startTest(self, test: unittest.TestCase):
        super().startTest(test)
        self._current_test_start = time.perf_counter()

    def addSuccess(self, test: unittest.TestCase):
        super().addSuccess(test)
        duration_ms = (time.perf_counter() - self._current_test_start) * 1000.0
        test_id = test.id()
        record = {
            "name": test._testMethodName,
            "class": test.__class__.__name__,
            "id": test_id,
            "status": "PASSED",
            "duration_ms": round(duration_ms, 2),
            "error": None
        }
        self.test_records.append(record)
        if self.verbose:
            pass_str = self._format("PASS", TerminalColor.GREEN)
            print(f"  {pass_str}  {test_id} ({duration_ms:.1f}ms)")

    def addFailure(self, test: unittest.TestCase, err):
        super().addFailure(test, err)
        duration_ms = (time.perf_counter() - self._current_test_start) * 1000.0
        test_id = test.id()
        err_msg = "".join(traceback.format_exception(*err))
        record = {
            "name": test._testMethodName,
            "class": test.__class__.__name__,
            "id": test_id,
            "status": "FAILED",
            "duration_ms": round(duration_ms, 2),
            "error": err_msg
        }
        self.test_records.append(record)
        fail_str = self._format("FAIL", TerminalColor.RED)
        print(f"  {fail_str}  {test_id} ({duration_ms:.1f}ms)")
        if self.verbose:
            print(f"{self._format(err_msg, TerminalColor.RED)}")
        if self.fail_fast:
            self.stop()

    def addError(self, test: unittest.TestCase, err):
        super().addError(test, err)
        duration_ms = (time.perf_counter() - self._current_test_start) * 1000.0
        test_id = test.id()
        err_msg = "".join(traceback.format_exception(*err))
        record = {
            "name": test._testMethodName,
            "class": test.__class__.__name__,
            "id": test_id,
            "status": "ERROR",
            "duration_ms": round(duration_ms, 2),
            "error": err_msg
        }
        self.test_records.append(record)
        err_str = self._format("ERROR", TerminalColor.RED)
        print(f"  {err_str} {test_id} ({duration_ms:.1f}ms)")
        if self.verbose:
            print(f"{self._format(err_msg, TerminalColor.RED)}")
        if self.fail_fast:
            self.stop()

    def addSkip(self, test: unittest.TestCase, reason: str):
        super().addSkip(test, reason)
        duration_ms = (time.perf_counter() - self._current_test_start) * 1000.0
        test_id = test.id()
        record = {
            "name": test._testMethodName,
            "class": test.__class__.__name__,
            "id": test_id,
            "status": "SKIPPED",
            "duration_ms": round(duration_ms, 2),
            "reason": reason
        }
        self.test_records.append(record)
        if self.verbose:
            skip_str = self._format("SKIP", TerminalColor.YELLOW)
            print(f"  {skip_str}  {test_id} ({reason})")


class E2ETestRunner:
    TIER_MAP = {
        "1": ("Tier 1: Feature Coverage (R1-R5)", TestTier1FeatureCoverage),
        "2": ("Tier 2: Boundary & Corner Cases", TestTier2BoundaryCorner),
        "3": ("Tier 3: Pairwise Combinations", TestTier3PairwiseCombinations),
        "4": ("Tier 4: Real-World Workloads", TestTier4RealWorldWorkloads),
    }

    def __init__(
        self,
        tiers: List[str],
        verbose: bool = False,
        fail_fast: bool = False,
        pattern_filter: Optional[str] = None,
        json_report_path: Optional[str] = None,
        color_mode: str = "auto"
    ):
        self.tiers = tiers
        self.verbose = verbose
        self.fail_fast = fail_fast
        self.pattern_filter = pattern_filter
        self.json_report_path = json_report_path
        self.use_color = TerminalColor.enable_colors(color_mode)

    def _format(self, text: str, color_code: str, bold: bool = False) -> str:
        if not self.use_color:
            return text
        b = TerminalColor.BOLD if bold else ""
        return f"{b}{color_code}{text}{TerminalColor.RESET}"

    def run(self) -> int:
        header_title = "NFL +EV BETTING APPLICATION — E2E TEST SUITE RUNNER"
        print("=" * 80)
        print(self._format(header_title, TerminalColor.CYAN, bold=True))
        print(f"Python {sys.version.split()[0]} | Mode: Standalone CLI Runner | Isolation: OFFLINE")
        print("=" * 80)
        print()

        selected_tiers = []
        if "all" in self.tiers:
            selected_tiers = ["1", "2", "3", "4"]
        else:
            for t in self.tiers:
                for sub in t.split(","):
                    sub = sub.strip()
                    if sub in self.TIER_MAP and sub not in selected_tiers:
                        selected_tiers.append(sub)

        if not selected_tiers:
            print(self._format("Error: No valid test tiers specified.", TerminalColor.RED))
            return 2

        overall_start_time = time.perf_counter()
        tier_summaries = {}
        all_passed = True
        total_executed = 0
        total_passed = 0
        total_failed = 0
        total_errors = 0
        total_skipped = 0

        for tier_key in selected_tiers:
            tier_name, test_class = self.TIER_MAP[tier_key]
            print(self._format(f"[{tier_name.upper()}]", TerminalColor.BOLD))

            loader = unittest.TestLoader()
            suite = unittest.TestSuite()

            # Load tests from test class
            method_names = loader.getTestCaseNames(test_class)
            for m in method_names:
                if self.pattern_filter:
                    full_id = f"{test_class.__name__}.{m}"
                    if self.pattern_filter.lower() not in full_id.lower():
                        continue
                suite.addTest(test_class(m))

            if suite.countTestCases() == 0:
                print(f"  No tests matched filter pattern: '{self.pattern_filter}'")
                print()
                continue

            tier_start = time.perf_counter()
            result = CustomTestResult(
                verbose=self.verbose,
                fail_fast=self.fail_fast,
                use_color=self.use_color
            )
            suite.run(result)
            tier_duration = time.perf_counter() - tier_start

            p_count = len([r for r in result.test_records if r["status"] == "PASSED"])
            f_count = len(result.failures)
            e_count = len(result.errors)
            s_count = len(result.skipped)
            t_count = len(result.test_records)

            total_executed += t_count
            total_passed += p_count
            total_failed += f_count
            total_errors += e_count
            total_skipped += s_count

            if f_count > 0 or e_count > 0:
                all_passed = False

            tier_summaries[tier_key] = {
                "name": tier_name,
                "total": t_count,
                "passed": p_count,
                "failed": f_count,
                "errors": e_count,
                "skipped": s_count,
                "duration_seconds": round(tier_duration, 3),
                "records": result.test_records
            }

            if not self.verbose:
                status_color = TerminalColor.GREEN if (f_count == 0 and e_count == 0) else TerminalColor.RED
                print(f"  {self._format('COMPLETED', status_color)} {t_count} tests in {tier_duration:.3f}s (Passed: {p_count}, Failed: {f_count}, Errors: {e_count})")
            print()

            if self.fail_fast and (f_count > 0 or e_count > 0):
                print(self._format("Execution aborted due to --fail-fast flag.", TerminalColor.YELLOW))
                break

        overall_duration = time.perf_counter() - overall_start_time

        # Print Execution Summary Table
        print("=" * 80)
        print(self._format("                             EXECUTION SUMMARY", TerminalColor.BOLD))
        print("=" * 80)
        table_header = f"+------------------------------------+-------+--------+--------+---------+--------+----------+"
        col_headers  = f"| Test Tier                          | Total | Passed | Failed | Skipped | Errors | Duration |"
        print(table_header)
        print(col_headers)
        print(table_header)

        for tier_key in selected_tiers:
            if tier_key not in tier_summaries:
                continue
            ts = tier_summaries[tier_key]
            tier_label = ts["name"][:34].ljust(34)
            tot_str = str(ts["total"]).rjust(5)
            pas_str = str(ts["passed"]).rjust(6)
            fai_str = str(ts["failed"]).rjust(6)
            ski_str = str(ts["skipped"]).rjust(7)
            err_str = str(ts["errors"]).rjust(6)
            dur_str = f"{ts['duration_seconds']:.3f}s".rjust(8)
            print(f"| {tier_label} | {tot_str} | {pas_str} | {fai_str} | {ski_str} | {err_str} | {dur_str} |")

        print(table_header)
        grand_label = "GRAND TOTAL".ljust(34)
        gtot = str(total_executed).rjust(5)
        gpas = str(total_passed).rjust(6)
        gfai = str(total_failed).rjust(6)
        gski = str(total_skipped).rjust(7)
        gerr = str(total_errors).rjust(6)
        gdur = f"{overall_duration:.3f}s".rjust(8)
        print(f"| {self._format(grand_label, TerminalColor.BOLD)} | {gtot} | {gpas} | {gfai} | {gski} | {gerr} | {gdur} |")
        print(table_header)
        print()

        pass_rate = (total_passed / max(1, total_executed)) * 100.0
        if all_passed and total_executed > 0:
            status_msg = f"STATUS: ALL TESTS PASSED ({pass_rate:.1f}% Pass Rate) — Exit Code 0"
            print(self._format(status_msg, TerminalColor.GREEN, bold=True))
            exit_code = 0
        else:
            status_msg = f"STATUS: TEST SUITE FAILED ({total_failed} failures, {total_errors} errors) — Exit Code 1"
            print(self._format(status_msg, TerminalColor.RED, bold=True))
            exit_code = 1
        print("=" * 80)

        # JSON Report generation
        if self.json_report_path:
            report_data = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "summary": {
                    "total": total_executed,
                    "passed": total_passed,
                    "failed": total_failed,
                    "skipped": total_skipped,
                    "errors": total_errors,
                    "pass_rate_pct": round(pass_rate, 2),
                    "duration_seconds": round(overall_duration, 4),
                    "exit_code": exit_code
                },
                "tiers": tier_summaries
            }
            try:
                with open(self.json_report_path, "w", encoding="utf-8") as f:
                    json.dump(report_data, f, indent=2)
                print(f"JSON Report written to: {self.json_report_path}")
            except Exception as e:
                print(self._format(f"Failed to write JSON report: {e}", TerminalColor.RED))

        return exit_code


def parse_args():
    parser = argparse.ArgumentParser(
        description="NFL +EV Betting Application - Comprehensive E2E Test Suite Runner"
    )
    parser.add_argument(
        "--tier", "-t",
        default="all",
        help="Test tier(s) to execute (comma-separated e.g. '1,2' or 'all'). Default: 'all'"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable detailed per-test execution logging with execution timing"
    )
    parser.add_argument(
        "--json-report", "-j",
        nargs="?",
        const="test_report.json",
        default=None,
        metavar="FILE",
        help="Output structured JSON test execution report to FILE (default: 'test_report.json')"
    )
    parser.add_argument(
        "--fail-fast", "-x",
        action="store_true",
        help="Stop test execution immediately upon first failure"
    )
    parser.add_argument(
        "--filter", "-k",
        default=None,
        metavar="PATTERN",
        help="Filter tests by substring pattern in test method or class name"
    )
    parser.add_argument(
        "--color",
        choices=["auto", "always", "never"],
        default="auto",
        help="Control ANSI colorized terminal output (default: 'auto')"
    )
    return parser.parse_args()


def main():
    args = parse_args()
    runner = E2ETestRunner(
        tiers=[args.tier],
        verbose=args.verbose,
        fail_fast=args.fail_fast,
        pattern_filter=args.filter,
        json_report_path=args.json_report,
        color_mode=args.color
    )
    exit_code = runner.run()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
