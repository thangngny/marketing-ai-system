"""
ElevenLabs Audio & Voiceover Controller for Buzz Marketing Agents.
Supports:
  - Account info & character quota check
  - Listing available voices & models
  - Vietnamese & multilingual TTS generation (eleven_multilingual_v2, eleven_turbo_v2_5)
  - Direct attachment to Buzz channels via Blossom media
"""
import sys
import os
import json
import argparse
import requests
from pathlib import Path

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Add marketing-system to path for connector and credential reuse
sys.path.append(r"C:\Users\Admin\marketing-ai-system\src")

from marketing_system.credentials import read_credential

DEFAULT_VOICE_ID = "EXAVITQu4vr4xnSDxMaL"  # Sarah - Mature, Reassuring, Confident
DEFAULT_MODEL_ID = "eleven_v4"              # Eleven v4 flagship model (90+ languages, emotional audio tags)


def get_api_key() -> str:
    key = os.environ.get("ELEVENLABS_API_KEY") or os.environ.get("ELEVEN_API_KEY")
    if not key:
        key = read_credential("ELEVENLABS_API_KEY") or read_credential("ELEVEN_API_KEY")
    if not key:
        print("Error: ELEVENLABS_API_KEY is not configured.", file=sys.stderr)
        sys.exit(1)
    return key.strip()


def get_headers() -> dict[str, str]:
    return {
        "xi-api-key": get_api_key(),
        "Accept": "application/json",
    }


def cmd_info(args):
    headers = get_headers()
    r = requests.get("https://api.elevenlabs.io/v1/user", headers=headers, timeout=15)
    r.raise_for_status()
    user_data = r.json()
    sub = user_data.get("subscription", {})
    tier = sub.get("tier", "unknown")
    count = sub.get("character_count", 0)
    limit = sub.get("character_limit", 0)
    remaining = max(0, limit - count)
    name = user_data.get("first_name", "User")

    print(f"=== ElevenLabs Account Info ===")
    print(f"User: {name}")
    print(f"Tier: {tier.upper()}")
    print(f"Character Usage: {count:,} / {limit:,} ({remaining:,} remaining)")
    print(f"Status: {sub.get('status', 'active')}")


def cmd_voices(args):
    headers = get_headers()
    r = requests.get("https://api.elevenlabs.io/v1/voices", headers=headers, timeout=20)
    r.raise_for_status()
    voices = r.json().get("voices", [])

    if args.query:
        q = args.query.lower()
        voices = [v for v in voices if q in v.get("name", "").lower() or q in json.dumps(v.get("labels", {})).lower()]
    if args.gender:
        g = args.gender.lower()
        voices = [v for v in voices if v.get("labels", {}).get("gender", "").lower() == g]

    print(f"Found {len(voices)} matching voices:")
    for v in voices[:args.limit]:
        labels = v.get("labels", {})
        gender = labels.get("gender", "unknown")
        accent = labels.get("accent", "standard")
        desc = labels.get("descriptive", "")
        print(f" - [{v.get('name')}] ID: {v.get('voice_id')} | {gender}, {accent} ({desc})")


def cmd_models(args):
    headers = get_headers()
    r = requests.get("https://api.elevenlabs.io/v1/models", headers=headers, timeout=15)
    r.raise_for_status()
    models = r.json()
    print(f"Available ElevenLabs Models ({len(models)}):")
    for m in models:
        can_tts = m.get("can_do_text_to_speech", False)
        if can_tts:
            langs = [l.get("language_id") for l in m.get("languages", [])]
            has_vi = "vi" in langs
            rate = m.get("model_rates", {}).get("character_cost_multiplier", 1.0)
            vi_flag = " [Supports Vietnamese]" if has_vi else ""
            print(f" - [{m.get('model_id')}] {m.get('name')} (rate: {rate}x){vi_flag}")


def cmd_tts(args):
    key = get_api_key()
    headers = {
        "xi-api-key": key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    voice_id = args.voice_id or DEFAULT_VOICE_ID
    model_id = args.model_id or DEFAULT_MODEL_ID

    payload = {
        "text": args.text,
        "model_id": model_id,
        "voice_settings": {
            "stability": args.stability,
            "similarity_boost": args.similarity,
        },
    }

    output_path = args.output
    if not output_path:
        import tempfile
        output_path = os.path.join(tempfile.gettempdir(), f"elevenlabs_{int(time.time())}.mp3")

    print(f"Synthesizing speech via ElevenLabs...")
    print(f"Text ({len(args.text)} chars): '{args.text[:60]}...'")
    print(f"Voice ID: {voice_id} | Model: {model_id}")

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128"
    res = requests.post(url, headers=headers, json=payload, timeout=60)
    res.raise_for_status()

    with open(output_path, "wb") as f:
        f.write(res.content)

    file_size = os.path.getsize(output_path)
    print(f"SUCCESS! Audio saved to: {output_path} ({file_size:,} bytes)")

    if args.channel:
        post_audio_to_buzz(args.channel, args.text, output_path)


def post_audio_to_buzz(channel_id: str, text: str, audio_file: str):
    import subprocess
    import tempfile
    import time

    private_key = os.environ.get("BUZZ_PRIVATE_KEY")
    if not private_key:
        print("Note: BUZZ_PRIVATE_KEY environment variable not set. Skipping channel broadcast.", file=sys.stderr)
        return

    blossom_file = audio_file
    temp_mp4 = None
    if not audio_file.endswith(".mp4"):
        temp_mp4 = os.path.join(tempfile.gettempdir(), f"vo_{int(time.time())}.mp4")
        ff_cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=0x1E1E2E:s=720x720:r=25",
            "-i", audio_file,
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k",
            "-map_metadata", "-1", "-fflags", "+bitexact",
            "-movflags", "+faststart", "-shortest", temp_mp4
        ]
        try:
            subprocess.run(ff_cmd, capture_output=True, check=True)
            blossom_file = temp_mp4
        except Exception as e:
            print(f"Warning: could not convert audio to Blossom MP4: {e}", file=sys.stderr)

    msg = f"🎙️ **Audio Voiceover AI từ ElevenLabs:**\n\n> \"{text}\"\n\n(Phát trực tiếp ngay trong app Buzz):"
    cmd = [
        "buzz",
        "--relay", "https://phamgianam.communities.buzz.xyz",
        "--private-key", private_key,
        "messages", "send",
        "--channel", channel_id,
        "--content", msg,
        "--file", blossom_file,
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(f"Directly published audio file to Buzz channel {channel_id}")
    except Exception as exc:
        print(f"Failed to publish audio to Buzz channel: {exc}", file=sys.stderr)
    finally:
        if temp_mp4 and os.path.exists(temp_mp4):
            try:
                os.remove(temp_mp4)
            except Exception:
                pass


def main():
    import time
    parser = argparse.ArgumentParser(description="ElevenLabs Voice & Audio Controller")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # Info
    p_info = sub.add_parser("info", help="Check ElevenLabs account & character quota")
    p_stat = sub.add_parser("status", help="Check ElevenLabs account & character quota")

    # Voices
    p_voices = sub.add_parser("voices", help="List available ElevenLabs voices")
    p_voices.add_argument("--query", "-q", default=None, help="Filter by name or keyword")
    p_voices.add_argument("--gender", "-g", default=None, choices=["male", "female"], help="Filter by gender")
    p_voices.add_argument("--limit", "-l", type=int, default=20, help="Max voices to display")

    # Models
    p_models = sub.add_parser("models", help="List available synthesis models")

    # TTS
    p_tts = sub.add_parser("tts", help="Synthesize text to speech MP3 audio")
    p_tts.add_argument("--text", "-t", required=True, help="Text to speak")
    p_tts.add_argument("--voice-id", "-v", default=DEFAULT_VOICE_ID, help="Voice ID (default: Sarah)")
    p_tts.add_argument("--model-id", "-m", default=DEFAULT_MODEL_ID, help="Model ID (default: eleven_multilingual_v2)")
    p_tts.add_argument("--stability", type=float, default=0.5, help="Voice stability (0.0 to 1.0)")
    p_tts.add_argument("--similarity", type=float, default=0.75, help="Voice similarity boost (0.0 to 1.0)")
    p_tts.add_argument("--output", "-o", default=None, help="Output MP3 file path")
    p_tts.add_argument("--channel", "-c", default=None, help="Buzz channel UUID to broadcast audio")

    args = parser.parse_args()
    if args.cmd in ("info", "status"):
        cmd_info(args)
    elif args.cmd == "voices":
        cmd_voices(args)
    elif args.cmd == "models":
        cmd_models(args)
    elif args.cmd == "tts":
        cmd_tts(args)


if __name__ == "__main__":
    main()
