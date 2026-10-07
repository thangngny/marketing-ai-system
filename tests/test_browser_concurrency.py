import concurrent.futures
import time
import sys
from pathlib import Path

base_dir = Path(r"C:\Users\Admin\marketing-ai-system\x-context-intelligence")
sys.path.insert(0, str(base_dir))

from src.core.browser_worker import BrowserLock

def worker_task(agent_id, hold_time):
    start = time.time()
    print(f"[{agent_id}] Requesting browser lock...")
    with BrowserLock(job_id=f"job_{agent_id}", timeout=10) as lock:
        acquired = time.time()
        print(f"[{agent_id}] Acquired lock after {acquired - start:.2f}s, holding for {hold_time}s...")
        time.sleep(hold_time)
        print(f"[{agent_id}] Releasing lock...")
    released = time.time()
    print(f"[{agent_id}] Lock released at {released - start:.2f}s total.")
    return agent_id, acquired - start, released - start

def test_concurrent_agents():
    print("=== TESTING TWO CONCURRENT AGENTS SHARING BROWSER LOCK ===")
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(worker_task, "Agent_Research_Intelligence", 1.5)
        # Start agent 2 immediately after
        time.sleep(0.1)
        f2 = executor.submit(worker_task, "Agent_Strategy", 1.0)

        r1 = f1.result()
        r2 = f2.result()

    print(f"\nResult Agent 1: Wait={r1[1]:.2f}s, Total={r1[2]:.2f}s")
    print(f"Result Agent 2: Wait={r2[1]:.2f}s, Total={r2[2]:.2f}s")

    # Agent 2 must have waited at least 1.3s for Agent 1 to finish
    assert r2[1] >= 1.3, f"Agent 2 did not wait for Agent 1 (wait time: {r2[1]}s)"
    print("CONCURRENCY MUTEX TEST PASSED: Zero profile collisions, perfect serial queueing!")

if __name__ == "__main__":
    test_concurrent_agents()
