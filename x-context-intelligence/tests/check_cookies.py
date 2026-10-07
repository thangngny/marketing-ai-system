from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile

cookie_file = r"C:\Users\Admin\.buzz\chrome_profiles\Buzz-X-Research\Default\Network\Cookies"
if not os.path.exists(cookie_file):
    print("No cookie file found")
    exit(0)

tmp_file = os.path.join(tempfile.gettempdir(), "cookies_check.db")
try:
    shutil.copy2(cookie_file, tmp_file)
    conn = sqlite3.connect(tmp_file)
    cur = conn.cursor()
    cur.execute("SELECT host_key, name FROM cookies WHERE name in ('auth_token', 'ct0', 'twid')")
    rows = cur.fetchall()
    print("Auth cookies count:", len(rows))
    for r in rows:
        print(f" - Host: {r[0]} | Cookie: {r[1]}")
    conn.close()
finally:
    if os.path.exists(tmp_file):
        os.remove(tmp_file)
