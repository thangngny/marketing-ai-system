"""
Higgsfield AI Cinematic Video Controller for Buzz Marketing Agents.
Supports:
  - API connectivity probe and authentication status
  - Asynchronous Text-to-Video & Image-to-Video generation (Kling 3.0, Wan 2.7, LTX-2.5)
  - Polling and status tracking via request_id
  - Automatic download and Blossom upload to Buzz channels
"""
import sys
import os
import json
import time
import argparse
import requests
from pathlib import Path

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Add marketing-system to path for credential reuse
sys.path.append(r"C:\Users\Admin\marketing-ai-system\src")
from marketing_system.credentials import read_credential

DEFAULT_MODEL = "kling-video/v3.0-turbo/text-to-video"


def get_api_key() -> str:
    key = os.environ.get("HF_KEY") or os.environ.get("HIGGSFIELD_API_KEY")
    if not key:
        key = read_credential("HF_KEY") or read_credential("HIGGSFIELD_KEY")
    if not key:
        print("Error: Higgsfield API key (HF_KEY) is not configured.", file=sys.stderr)
        sys.exit(1)
    return key.strip()


def cmd_status(args):
    from higgsfield_client import SyncClient
    key = get_api_key()
    client = SyncClient(api_key=key)
    try:
        r = client._client.post("/files/generate-upload-url", json={"content_type": "image/jpeg"})
        if r.status_code == 200:
            print("=== Higgsfield API Status ===")
            print("Connection: ONLINE")
            print("Authentication: VALID")
            print("Endpoint: https://api.higgsfield.ai")
        else:
            print(f"Higgsfield status check failed with HTTP {r.status_code}: {r.text}", file=sys.stderr)
            sys.exit(1)
    except Exception as exc:
        print(f"Error connecting to Higgsfield API: {exc}", file=sys.stderr)
        sys.exit(1)


def cmd_generate(args):
    from higgsfield_client import SyncClient
    key = get_api_key()
    client = SyncClient(api_key=key)

    model = args.model or DEFAULT_MODEL
    arguments = {
        "prompt": args.prompt,
        "duration": args.duration,
        "aspect_ratio": args.ratio,
    }
    if args.image_url:
        arguments["image_url"] = args.image_url

    print(f"Submitting Higgsfield video generation...")
    print(f"Model: {model}")
    print(f"Prompt: '{args.prompt[:80]}...'")
    print(f"Ratio: {args.ratio} | Duration: {args.duration}s")

    controller = client.submit(application=model, arguments=arguments)
    request_id = controller.request_id
    status_url = controller.status_url
    print(f"SUCCESS! Request ID: {request_id}")
    print(f"Status URL: {status_url}")

    if args.wait:
        print("Waiting for video rendering to complete...")
        data = wait_for_completion(controller, poll_interval=args.poll_interval, max_wait=args.timeout)
        video_url = extract_video_url(data)
        print(f"RENDER COMPLETED! Video URL: {video_url}")

        if args.output:
            download_video(video_url, args.output)

        if args.channel:
            post_video_to_buzz(args.channel, args.prompt, video_url)


def wait_for_completion(controller, poll_interval: float = 10.0, max_wait: float = 600.0):
    deadline = time.monotonic() + max_wait
    while True:
        status_obj = controller.status()
        status_name = status_obj.__class__.__name__.lower()
        print(f"Status: {status_name}...")

        if status_name == "completed":
            return controller.get()
        if status_name in {"failed", "cancelled", "nsfw"}:
            raise RuntimeError(f"Higgsfield generation ended with status: {status_name}")

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"Timed out waiting for Higgsfield request after {max_wait}s")
        time.sleep(min(poll_interval, remaining))


def extract_video_url(data) -> str:
    if isinstance(data, dict):
        if "video_url" in data:
            return data["video_url"]
        if "url" in data:
            return data["url"]
        if "output" in data and isinstance(data["output"], dict):
            return data["output"].get("url") or data["output"].get("video_url")
        if "output" in data and isinstance(data["output"], list) and len(data["output"]) > 0:
            item = data["output"][0]
            if isinstance(item, str):
                return item
            if isinstance(item, dict):
                return item.get("url") or item.get("video_url")
    return str(data)


def download_video(url: str, output_path: str):
    print(f"Downloading video from {url} to {output_path}...")
    r = requests.get(url, stream=True, timeout=60)
    r.raise_for_status()
    with open(output_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)
    print(f"Downloaded successfully: {output_path} ({os.path.getsize(output_path)} bytes)")


def post_video_to_buzz(channel_id: str, prompt: str, video_url: str):
    import subprocess
    import tempfile

    private_key = os.environ.get("BUZZ_PRIVATE_KEY")
    if not private_key:
        print("Note: BUZZ_PRIVATE_KEY not set. Skipping Buzz broadcast.", file=sys.stderr)
        return

    # Download and normalize with FastStart
    temp_raw = os.path.join(tempfile.gettempdir(), f"hf_raw_{int(time.time())}.mp4")
    temp_clean = os.path.join(tempfile.gettempdir(), f"hf_clean_{int(time.time())}.mp4")
    try:
        download_video(video_url, temp_raw)
        ff_cmd = [
            "ffmpeg", "-y", "-i", temp_raw,
            "-c", "copy", "-map_metadata", "-1",
            "-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact",
            "-movflags", "+faststart", temp_clean
        ]
        subprocess.run(ff_cmd, capture_output=True, check=True)

        msg = f"🎬 **Video B-Roll Điện ảnh từ Higgsfield AI:**\n\n> Prompt: \"{prompt}\"\n\n(Phát trực tiếp ngay trong app Buzz):"
        cmd = [
            "buzz",
            "--relay", "https://phamgianam.communities.buzz.xyz",
            "--private-key", private_key,
            "messages", "send",
            "--channel", channel_id,
            "--content", msg,
            "--file", temp_clean,
        ]
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(f"Directly published Higgsfield video to Buzz channel {channel_id}")
    except Exception as exc:
        print(f"Failed to post to Buzz: {exc}", file=sys.stderr)
    finally:
        for f in (temp_raw, temp_clean):
            if os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass


def cmd_poll(args):
    from higgsfield_client import SyncClient
    key = get_api_key()
    client = SyncClient(api_key=key)
    controller = client.get_request_controller(args.request_id)
    status_obj = controller.status()
    status_name = status_obj.__class__.__name__
    print(f"Request ID: {args.request_id}")
    print(f"Status: {status_name}")
    if status_name.lower() == "completed":
        data = controller.get()
        print("Result:", json.dumps(data, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Higgsfield AI Video Controller")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # Status
    sub.add_parser("status", help="Check Higgsfield API connection & authentication")

    # Generate
    p_gen = sub.add_parser("generate", help="Generate cinematic video")
    p_gen.add_argument("--prompt", "-p", required=True, help="Scene description prompt")
    p_gen.add_argument("--model", "-m", default=DEFAULT_MODEL, help="Model endpoint (default: Kling 3.0 Turbo)")
    p_gen.add_argument("--image-url", default=None, help="Optional source image for image-to-video")
    p_gen.add_argument("--duration", "-d", type=int, default=5, help="Video duration in seconds (default: 5)")
    p_gen.add_argument("--ratio", "-r", default="9:16", choices=["9:16", "16:9", "1:1"], help="Aspect ratio")
    p_gen.add_argument("--wait", action="store_true", help="Poll until generation completes")
    p_gen.add_argument("--timeout", type=int, default=600, help="Max wait seconds")
    p_gen.add_argument("--poll-interval", type=int, default=10, help="Polling interval seconds")
    p_gen.add_argument("--output", "-o", default=None, help="Output MP4 path")
    p_gen.add_argument("--channel", "-c", default=None, help="Buzz channel UUID to broadcast finished video")

    # Poll
    p_poll = sub.add_parser("poll", help="Check status of existing request")
    p_poll.add_argument("request_id", help="Higgsfield request ID")

    args = parser.parse_args()
    if args.cmd == "status":
        cmd_status(args)
    elif args.cmd == "generate":
        cmd_generate(args)
    elif args.cmd == "poll":
        cmd_poll(args)


if __name__ == "__main__":
    main()
