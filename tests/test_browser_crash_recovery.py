import subprocess
import sys
import time
from pathlib import Path

base_dir = Path(r"C:\Users\Admin\marketing-ai-system\x-context-intelligence")
sys.path.insert(0, str(base_dir))
from src.core.browser_worker import BrowserLock

def test_crash_recovery():
    # Spawn a crasher process that acquires the lock and immediately dies via os._exit
    crasher_code = """
import sys, os
from pathlib import Path
sys.path.insert(0, r"C:\\Users\\Admin\\marketing-ai-system\\x-context-intelligence")
from src.core.browser_worker import BrowserLock

lock = BrowserLock(job_id="crashed_job", timeout=5)
lock.acquire()
print("LOCKED", flush=True)
os._exit(42)
"""
    p = subprocess.Popen([sys.executable, "-c", crasher_code], stdout=subprocess.PIPE, text=True)
    line = p.stdout.readline().strip()
    assert line == "LOCKED"
    p.wait()
    assert p.returncode == 42
    print("Crashed process terminated abruptly with code 42.")

    # Now attempt to acquire with a survivor process
    start = time.time()
    with BrowserLock(job_id="survivor_job", timeout=5) as lock:
        elapsed = time.time() - start
        print(f"Survivor acquired abandoned lock in {elapsed:.3f}s!")
        assert elapsed < 1.0

    print("CRASH RECOVERY TEST PASSED: Crashed task safely released lock via kernel WAIT_ABANDONED!")

if __name__ == "__main__":
    test_crash_recovery()
