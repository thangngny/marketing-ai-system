import os
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
import httpx
from marketing_system.credentials import read_credential, write_credential

CLIENT_ID = read_credential("GOOGLE_DRIVE_CLIENT_ID")
CLIENT_SECRET = read_credential("GOOGLE_DRIVE_CLIENT_SECRET")
PORT = 53683
REDIRECT_URI = f"http://127.0.0.1:{PORT}"

SCOPE = "https://www.googleapis.com/auth/drive https://www.googleapis.com/auth/drive.file https://www.googleapis.com/auth/drive.readonly"

auth_params = {
    "client_id": CLIENT_ID,
    "redirect_uri": REDIRECT_URI,
    "response_type": "code",
    "scope": SCOPE,
    "access_type": "offline",
    "prompt": "consent",
}
auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(auth_params)}"

print(f"AUTH_URL_START: {auth_url}", flush=True)

import webbrowser
import subprocess
try:
    subprocess.Popen(f'start "" "{auth_url}"', shell=True)
except Exception:
    pass
webbrowser.open(auth_url)

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        code = query.get("code", [None])[0]
        if code:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            success_html = """
            <html><body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                <h1 style="color: #10b981;">&#10004; Đã cấp quyền Google Drive thành công!</h1>
                <p style="font-size: 18px; color: #374151;">Toàn bộ 23 AI Agents trong hệ sinh thái Buzz hiện đã có quyền đọc, tìm kiếm và trích xuất dữ liệu từ Google Drive.</p>
                <p style="color: #6b7280;">Bạn có thể đóng tab trình duyệt này lại và quay trở về ứng dụng.</p>
            </body></html>
            """
            self.wfile.write(success_html.encode("utf-8"))
            print(f"CODE_RECEIVED: {code}", flush=True)
            self.server.code_received = code
            
            # Exchange code
            resp = httpx.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": CLIENT_ID,
                    "client_secret": CLIENT_SECRET,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": REDIRECT_URI,
                }
            )
            print(f"EXCHANGE_STATUS: {resp.status_code}", flush=True)
            data = resp.json()
            if "refresh_token" in data:
                write_credential("GOOGLE_DRIVE_REFRESH_TOKEN", data["refresh_token"])
                print("SUCCESS_SAVED_REFRESH_TOKEN", flush=True)
            else:
                print(f"NO_REFRESH_TOKEN: {data}", flush=True)
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Waiting for authorization...")

    def log_message(self, format, *args):
        return

server = HTTPServer(("127.0.0.1", PORT), Handler)
server.code_received = None
print(f"Listening on {REDIRECT_URI}...", flush=True)
while not server.code_received:
    server.handle_request()
print("Reauth server finished cleanly.", flush=True)

