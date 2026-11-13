import subprocess
import sys
import time
from pathlib import Path
import pytest

base_dir = Path(__file__).resolve().parent.parent / "x-context-intelligence"
if str(base_dir) not in sys.path:
    sys.path.insert(0, str(base_dir))

try:
    from src.core.browser_worker import BrowserLock
except (ImportError, ModuleNotFoundError, AttributeError) as e:
    pytest.skip(f"BrowserLock or dependencies unavailable: {e}", allow_module_level=True)

def test_crash_recovery():
    # Spawn a crasher process that acquires the lock and immediately dies via os._exit
    escaped_base_dir = str(base_dir).replace('\\', '\\\\')
    crasher_code = f"""
import sys, os
from pathlib import Path
sys.path.insert(0, "{escaped_base_dir}")
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
