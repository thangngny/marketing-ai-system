#!/usr/bin/env python3
"""
Enterprise Video Production Pipeline CLI.
Coordinates Multi-Modal AI generation (HeyGen, ElevenLabs, Higgsfield, Pexels, Whisper, FFmpeg),
renders dynamic kinetic subtitles with auto-ducking BGM, publishes to Buzz Blossom & TikTok,
and outputs a complete Technology Attribution breakdown.
"""

import argparse
import sys
from pathlib import Path

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Add src to sys.path
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from marketing_system.video import VideoComposer, VideoProductionConfig


def main():
    parser = argparse.ArgumentParser(
        description="Unified Enterprise Video Production Pipeline with Technology Attribution"
    )
    parser.add_argument("--title", required=True, help="Video title and topic")
    parser.add_argument("--script", required=True, help="Script / voiceover text in Vietnamese")
    parser.add_argument(
        "--mode",
        choices=["hybrid", "avatar", "cinematic", "motion"],
        default="hybrid",
        help="Production mode: hybrid (Stock + AI), avatar (HeyGen MC Lina), cinematic (Higgsfield Kling 3.0), motion (HyperFrames)",
    )
    parser.add_argument(
        "--ratio",
        choices=["9:16", "16:9"],
        default="9:16",
        help="Video aspect ratio: 9:16 (TikTok/Reels/Shorts) or 16:9 (YouTube standard)",
    )
    parser.add_argument("--bgm", default=None, help="Path to background music file")
    parser.add_argument("--no-subtitles", action="store_true", help="Disable kinetic subtitles")
    parser.add_argument("--publish-tiktok", action="store_true", help="Publish or stage to TikTok directly")
    parser.add_argument("--publish-youtube", action="store_true", help="Publish or stage to YouTube")
    parser.add_argument("--outdir", default=None, help="Custom output directory")

    args = parser.parse_args()

    channels = []
    if args.publish_tiktok:
        channels.append("tiktok")
    if args.publish_youtube:
        channels.append("youtube")

    config = VideoProductionConfig(
        title=args.title,
        script=args.script,
        mode=args.mode,
        aspect_ratio=args.ratio,
        bgm_path=args.bgm,
        enable_subtitles=not args.no_subtitles,
        auto_publish_channels=channels,
        output_dir=Path(args.outdir) if args.outdir else None,
    )

    print("=" * 70)
    print("🚀 BẮT ĐẦU DÂY CHUYỀN SẢN XUẤT VIDEO TỰ ĐỘNG (MULTI-MODAL VIDEO PIPELINE)")
    print(f"Tiêu đề: {config.title}")
    print(f"Chế độ: {config.mode.upper()} | Tỷ lệ: {config.aspect_ratio}")
    print("=" * 70)

    composer = VideoComposer()
    result = composer.produce(config)

    print("\n" + "=" * 70)
    print(result.summary_report)
    print("=" * 70)


if __name__ == "__main__":
    main()
