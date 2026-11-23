"""
Master test runner for oxDesktop:
Executes both:
1. tests/test_e2e_suite.py (E2E architecture, config, proxy, anti-delete, UI, installer, versioning)
2. tests/test_plugin_full_suite.py (Python SDK, sandboxing, security, and plugin lifecycle)
"""

import subprocess
import sys
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    print("=" * 70)
    print(" oxDesktop Unified Master Test Runner")
    print("=" * 70)

    # 1. Run E2E Test Suite
    e2e_script = os.path.join(REPO_ROOT, "tests", "test_e2e_suite.py")
    print(f"\n[1/2] Running E2E Architecture Suite: {e2e_script}...")
    res_e2e = subprocess.run([sys.executable, e2e_script], cwd=REPO_ROOT)
    if res_e2e.returncode != 0:
        print("\n[-] E2E Architecture Suite FAILED!")
        sys.exit(res_e2e.returncode)

    # 2. Run Plugin & Security Suite
    plugin_script = os.path.join(REPO_ROOT, "tests", "test_plugin_full_suite.py")
    print(f"\n[2/2] Running Plugin & Security Suite: {plugin_script}...")
    res_plugin = subprocess.run([sys.executable, plugin_script], cwd=REPO_ROOT)
    if res_plugin.returncode != 0:
        print("\n[-] Plugin & Security Suite FAILED!")
        sys.exit(res_plugin.returncode)

    print("\n" + "=" * 70)
    print(">>> ALL TEST SUITES PASSED CLEANLY (100% SUCCESS) <<<")
    print("=" * 70)
    sys.exit(0)


if __name__ == "__main__":
    main()
