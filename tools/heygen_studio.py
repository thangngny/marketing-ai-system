"""Native REST API v3 HeyGen controller for Minh Van Logistics."""
import sys
import os
import json
import time
import argparse
import requests
import httpx

# Ensure stdout can print UTF-8 on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Add marketing-system to path for connector reuse
sys.path.append(r"C:\Users\Admin\marketing-ai-system\src")

from marketing_system.connectors.heygen import HeyGenConnector
from marketing_system.config import Settings

LINA_AVATAR_ID = "f9f270fb70a84c669572001ef3aaee17"
LINA_VOICE_ID = "6acea87b5a0b45268e410b84a0aef7a1"

def get_live_conn():
    settings = Settings(environment="production")
    return HeyGenConnector(settings)

def cmd_api_info(args):
    conn = get_live_conn()
    r = conn.probe_live()
    print(f"Health: {r[1]}")
    res = conn.request(
        "GET",
        "https://api.heygen.com/v3/users/me",
        headers=conn._headers(),
        timeout=15.0,
    )
    res.raise_for_status()
    print("Account details:", json.dumps(res.json().get("data", {}), indent=2))

def cmd_api_avatars(args):
    conn = get_live_conn()
    avatars = conn.read("avatars", limit=10)
    print(f"Found {len(avatars)} avatars:")
    for a in avatars:
        print(f" - [{a.get('name')}] ID: {a.get('id')} (Gender: {a.get('gender')})")

def cmd_api_voices(args):
    conn = get_live_conn()
    voices = conn.read("voices", language="Vietnamese")
    print(f"Found {len(voices)} Vietnamese voices:")
    for v in voices:
        print(f" - [{v.get('name')}] ID: {v.get('voice_id')} (Gender: {v.get('gender')})")

def cmd_api_generate(args):
    conn = get_live_conn()
    print(f"Submitting video creation for: '{args.script[:50]}...'")
    print(f"Avatar: {args.avatar_id} | Voice: {args.voice_id} | Ratio: {args.ratio}")
    try:
        res = conn.create_video_draft(
            script=args.script,
            avatar_id=args.avatar_id,
            voice_id=args.voice_id,
            aspect_ratio=args.ratio,
            background_color=args.bg,
            title=args.title
        )
    except httpx.HTTPStatusError as exc:
        print(f"HeyGen API error {exc.response.status_code}: {exc.response.text}", file=sys.stderr)
        raise
    video_id = res.get("video_id")
    if not video_id:
        raise RuntimeError("HeyGen API response did not include a video_id")
    print(f"SUCCESS! Video ID: {video_id}")
    if args.wait:
        print("Waiting for video rendering to complete...")
        data = wait_for_video_completion(conn, video_id, poll_interval=10, max_wait=args.timeout)
        video_url = data.get("video_url")
        print(f"RENDER COMPLETED! Video URL: {video_url}")
        if args.download:
            if not video_url:
                raise RuntimeError("Completed HeyGen video response did not include a video_url")
            download_video(video_url, args.download)

def wait_for_video_completion(conn, video_id: str, poll_interval: float = 10, max_wait: float = 600):
    """Poll the REST API v3 video status until it reaches a terminal state."""
    deadline = time.monotonic() + max_wait
    while True:
        result = conn.read("video_status", video_id=video_id)
        if isinstance(result, list):
            data = result[0] if result else {}
        elif isinstance(result, dict) and isinstance(result.get("data"), dict):
            data = result["data"]
        else:
            data = result

        if not isinstance(data, dict):
            raise RuntimeError("Unexpected HeyGen video status response")

        status = str(data.get("status", "")).lower()
        if status == "completed":
            return data
        if status in {"failed", "canceled", "cancelled"}:
            detail = data.get("error") or data.get("message") or "no error details"
            raise RuntimeError(f"HeyGen video {video_id} ended with status {status}: {detail}")

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"Timed out waiting for HeyGen video {video_id} after {max_wait} seconds")
        time.sleep(min(poll_interval, remaining))

def cmd_api_status(args):
    conn = get_live_conn()
    data = conn.read("video_status", video_id=args.video_id)
    print(json.dumps(data, indent=2))

def download_video(url: str, output_path: str):
    print(f"Downloading video from {url} to {output_path}...")
    r = requests.get(url, stream=True, timeout=60)
    r.raise_for_status()
    with open(output_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)
    print(f"Downloaded successfully: {output_path} ({os.path.getsize(output_path)} bytes)")

def main():
    parser = argparse.ArgumentParser(description="HeyGen Native REST API v3 Controller")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # API commands
    p_info = sub.add_parser("api-info", help="Check API connection & credits")
    p_stat = sub.add_parser("status", help="Check API connection & credits")
    p_inf = sub.add_parser("info", help="Check API connection & credits")
    p_avatars = sub.add_parser("api-avatars", help="List available avatars")
    p_voices = sub.add_parser("api-voices", help="List Vietnamese voices")
    
    p_gen = sub.add_parser("api-generate", help="Generate video via API v3")
    p_gen.add_argument("--script", required=True, help="Spoken script text")
    p_gen.add_argument("--avatar-id", default=LINA_AVATAR_ID, help="Avatar ID (default: Lina)")
    p_gen.add_argument("--voice-id", default=LINA_VOICE_ID, help="Voice ID (default: Lina Vietnamese)")
    p_gen.add_argument("--ratio", default="9:16", choices=["9:16", "16:9"], help="Aspect ratio")
    p_gen.add_argument("--bg", default=None, help="Optional background color hex; omit to preserve the selected look's baked background")
    p_gen.add_argument("--title", default=None, help="Video title")
    p_gen.add_argument("--wait", action="store_true", help="Wait for render completion")
    p_gen.add_argument("--timeout", type=int, default=600, help="Max wait seconds")
    p_gen.add_argument("--download", default=None, help="Output path to download MP4")

    p_stat = sub.add_parser("api-status", help="Get video render status")
    p_stat.add_argument("video_id", help="HeyGen video ID")

    args = parser.parse_args()
    if args.cmd in ("api-info", "status", "info"):
        cmd_api_info(args)
    elif args.cmd == "api-avatars":
        cmd_api_avatars(args)
    elif args.cmd == "api-voices":
        cmd_api_voices(args)
    elif args.cmd == "api-generate":
        cmd_api_generate(args)
    elif args.cmd == "api-status":
        cmd_api_status(args)

if __name__ == "__main__":
    main()
