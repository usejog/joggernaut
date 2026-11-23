"""Run a test command many times while every core is busy. Prints failures."""
import os
import subprocess
import sys


BURN = "x = 0\nwhile True:\n    x = (x * 31 + 7) % 1000003\n"


def under_strain(cmd, cwd, runs, burners=None):
    n = burners or (os.cpu_count() or 2) * 2
    procs = [subprocess.Popen([sys.executable, "-c", BURN]) for _ in range(n)]
    failures = 0
    try:
        for _ in range(runs):
            r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
            if r.returncode != 0:
                failures += 1
    finally:
        for p in procs:
            p.kill()
        for p in procs:
            p.wait()
    return failures


if __name__ == "__main__":
    cwd, runs = sys.argv[1], int(sys.argv[2])
    cmd = [sys.executable, "-m", "unittest", "-q", "tests.test_debounce"]
    print("failures: %d of %d" % (under_strain(cmd, cwd, runs), runs))
