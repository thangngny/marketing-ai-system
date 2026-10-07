"""Technology Attribution Generator for Video Deliverables."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TechnologyAttribution:
    script_engine: str = "Content Planner AI (Hermes / Claude 3.5) — Cấu trúc Hook 3s & nhịp giữ chân người xem"
    voice_engine: str = "ElevenLabs Multilingual v2 — Giọng thuyết minh Studio tiếng Việt tự nhiên"
    avatar_engine: str | None = None
    broll_engine: str | None = None
    subtitle_engine: str = "OpenAI Whisper Local + FFmpeg libass — Nhận diện từ & phụ đề động viền vàng (Kinetic Karaoke)"
    audio_post_engine: str = "HyperFrames Audio Mixer — Tự động hạ âm lượng nhạc nền khi có giọng đọc (Auto-Ducking)"
    render_engine: str = "FFmpeg 9.0.1 — Render tăng tốc phần cứng (NVENC / H.264 60FPS)"
    storage_engine: str = "Buzz Blossom Media Server — Lưu trữ phân tán & phát video độ trễ thấp"
    distribution_engine: str = "TikTok Official Content Posting API v2 (Direct Post)"
    custom_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = {
            "Kịch bản & Cấu trúc Hook": self.script_engine,
            "Giọng đọc AI (Voiceover)": self.voice_engine,
            "Phụ đề động (Dynamic Subtitles)": self.subtitle_engine,
            "Xử lý âm thanh & Nhạc nền": self.audio_post_engine,
            "Động cơ Render Video": self.render_engine,
            "Lưu trữ & Streaming": self.storage_engine,
            "Phân phối & Đăng tải": self.distribution_engine,
        }
        if self.avatar_engine:
            data["MC / Avatar ảo"] = self.avatar_engine
        if self.broll_engine:
            data["Hình ảnh & B-roll Footage"] = self.broll_engine
        if self.custom_notes:
            data["Ghi chú kỹ thuật bổ sung"] = self.custom_notes
        return data


def build_attribution_report(
    title: str,
    duration_sec: float,
    resolution: str,
    blossom_url: str | None,
    local_path: str,
    attribution: TechnologyAttribution,
    social_status: dict[str, Any] | None = None,
) -> str:
    """Format an executive technical report describing all technologies combined in the video."""
    lines = [
        "## 🎬 BÁO CÁO XUẤT BẢN VIDEO & PHÂN TÍCH CÔNG NGHỆ TÍCH HỢP",
        "",
        f"**Tiêu đề**: {title}",
        f"**Thời lượng**: {duration_sec:.1f} giây | **Độ phân giải**: {resolution}",
        f"**Tệp cục bộ**: `{local_path}`",
    ]

    if blossom_url:
        lines.append(f"**Xem trực tuyến (Blossom Media Link)**: [{blossom_url}]({blossom_url})")

    lines.extend([
        "",
        "### 🛠️ CÁC CÔNG NGHỆ ĐÃ ĐƯỢC KẾT HỢP TRONG VIDEO NÀY:",
        "",
        "| Thành phần (Component) | Công nghệ / Nền tảng áp dụng | Vai trò trong quá trình tạo video |",
        "| :--- | :--- | :--- |",
        f"| **1. Kịch bản & Hook** | {attribution.script_engine} | Viết hook 3s đầu chống lướt qua, phân đoạn nhịp đọc và lời thoại |",
        f"| **2. Giọng đọc Studio** | {attribution.voice_engine} | Chuyển văn bản thành giọng đọc tự nhiên, chuẩn ngữ điệu tiếng Việt |",
    ])

    idx = 3
    if attribution.avatar_engine:
        lines.append(
            f"| **{idx}. MC / Avatar ảo** | {attribution.avatar_engine} | Tạo MC ảo phát biểu, đồng bộ khẩu hình môi (Lip-sync) chính xác |"
        )
        idx += 1

    if attribution.broll_engine:
        lines.append(
            f"| **{idx}. Visual B-roll** | {attribution.broll_engine} | Cung cấp cảnh quay điện ảnh/thực tế minh họa trực quan chủ đề |"
        )
        idx += 1

    lines.extend([
        f"| **{idx}. Phụ đề động** | {attribution.subtitle_engine} | Trích xuất timestamps từng từ, đục chữ viền vàng nổi bật kiểu CapCut |",
        f"| **{idx+1}. Xử lý âm thanh** | {attribution.audio_post_engine} | Tự động hạ nhạc nền -24dB khi có voice, tăng âm lượng khi ngắt câu |",
        f"| **{idx+2}. Bộ Render** | {attribution.render_engine} | Ghép nối timeline, tối ưu nén h264 bitrate cao cho TikTok & Shorts |",
        f"| **{idx+3}. Lưu trữ & Host** | {attribution.storage_engine} | Đưa video lên máy chủ phân tán Buzz, sinh link stream tức thì |",
    ])

    if attribution.distribution_engine:
        lines.append(
            f"| **{idx+4}. Đăng đa nền tảng** | {attribution.distribution_engine} | Đăng bài tự động lên TikTok/Reels mà không cần thao tác tay |"
        )

    if social_status:
        lines.extend([
            "",
            "### 📡 TRẠNG THÁI PHÂN PHỐI MẠNG XÃ HỘI:",
        ])
        for platform, info in social_status.items():
            lines.append(f"- **{platform.upper()}**: {info}")

    return "\n".join(lines)
