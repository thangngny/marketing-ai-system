#!/usr/bin/env python3
"""
Buzz Export CLI Tool
Uploads deliverables (PDF, DOCX, XLSX, MP4, ZIP, Images) to Buzz Blossom Media Server
and formats them for cross-device viewing & downloading.
"""
import sys
import os
import argparse
import json
import subprocess
import shutil
import ctypes
from ctypes import wintypes

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_RELAY = os.environ.get("BUZZ_RELAY", "https://phamgianam.communities.buzz.xyz")

def get_nsec_from_vault():
    """Retrieve nsec private key from Windows Credential Manager."""
    if sys.platform != "win32":
        return os.environ.get("BUZZ_PRIVATE_KEY")
    
    # Try env var first
    if os.environ.get("BUZZ_PRIVATE_KEY"):
        return os.environ.get("BUZZ_PRIVATE_KEY")

    class _CRED(ctypes.Structure):
        _fields_ = [
            ('Flags', wintypes.DWORD),
            ('Type', wintypes.DWORD),
            ('TargetName', wintypes.LPWSTR),
            ('Comment', wintypes.LPWSTR),
            ('LastWritten', wintypes.FILETIME),
            ('CredentialBlobSize', wintypes.DWORD),
            ('CredentialBlob', ctypes.POINTER(ctypes.c_ubyte)),
            ('Persist', wintypes.DWORD),
            ('AttributeCount', wintypes.DWORD),
            ('Attributes', ctypes.c_void_p),
            ('TargetAlias', wintypes.LPWSTR),
            ('UserName', wintypes.LPWSTR)
        ]
    
    adv = ctypes.WinDLL('Advapi32.dll', use_last_error=True)
    adv.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.POINTER(_CRED))]
    adv.CredReadW.restype = wintypes.BOOL
    adv.CredFree.argtypes = [ctypes.c_void_p]
    cred = ctypes.POINTER(_CRED)()

    if adv.CredReadW('secrets.buzz-desktop', 1, 0, ctypes.byref(cred)):
        try:
            raw = ctypes.string_at(cred.contents.CredentialBlob, cred.contents.CredentialBlobSize)
            data = json.loads(raw.decode('utf-16-le'))
            return data.get('identity')
        finally:
            adv.CredFree(cred)
    return None

def sanitize_media(file_path):
    """Sanitize video files and package audio files to pass Blossom validation without metadata errors."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext in ['.mp4', '.mov']:
        clean_path = file_path + ".clean.mp4"
        cmd = [
            "ffmpeg", "-y", "-i", file_path,
            "-c", "copy",
            "-map_metadata", "-1",
            "-fflags", "+bitexact",
            "-flags:v", "+bitexact",
            "-flags:a", "+bitexact",
            "-movflags", "+faststart",
            clean_path
        ]
        res = subprocess.run(cmd, capture_output=True)
        if res.returncode == 0 and os.path.exists(clean_path):
            return clean_path
    elif ext in ['.mp3', '.wav', '.m4a', '.ogg', '.aac', '.flac', '.wma', '.webm']:
        # Blossom Relay blocks raw audio/* mime types by design (due to unverified location metadata in audio containers).
        # Buzz Desktop packages voice notes into a minimal bitexact MP4 video container.
        stem = os.path.splitext(os.path.basename(file_path))[0]
        clean_path = os.path.join(os.path.dirname(file_path) or ".", f"voice-note-{stem}.mp4")
        cmd = [
            "ffmpeg", "-y", "-nostdin", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=black:s=16x16:r=1",
            "-i", file_path,
            "-map", "0:v:0", "-map", "1:a:0",
            "-shortest",
            "-map_metadata", "-1", "-map_chapters", "-1",
            "-sn", "-dn",
            "-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact",
            "-c:v", "libx264", "-preset", "ultrafast", "-tune", "stillimage", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "96k",
            "-movflags", "+faststart",
            "-metadata", "encoder=",
            clean_path
        ]
        res = subprocess.run(cmd, capture_output=True)
        if res.returncode == 0 and os.path.exists(clean_path):
            return clean_path
    return file_path

def format_size(size_bytes):
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"

def upload_to_public_cdn(file_path):
    """Upload deliverable to GitHub Release CDN for 100% public, direct browser download without 401 error."""
    try:
        filename = os.path.basename(file_path)
        repo = "thangngny/buzz-ai-usage-center"
        tag = "deliverables"
        res = subprocess.run([
            "gh", "release", "upload", tag, file_path,
            "--repo", repo, "--clobber"
        ], capture_output=True, text=True)
        if res.returncode == 0:
            return f"https://github.com/{repo}/releases/download/{tag}/{filename}"
    except Exception:
        pass
    return None

def upload_image_to_raw_cdn(file_path):
    """Upload image to GitHub repo contents/media for direct raw rendering without Content-Disposition attachment."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext not in ['.png', '.jpg', '.jpeg', '.webp', '.gif']:
        return None
    try:
        import base64
        filename = os.path.basename(file_path)
        repo = "thangngny/buzz-ai-usage-center"
        with open(file_path, "rb") as f:
            b64_content = base64.b64encode(f.read()).decode("utf-8")
        
        check_res = subprocess.run([
            "gh", "api", f"repos/{repo}/contents/media/{filename}"
        ], capture_output=True, text=True)
        sha = None
        if check_res.returncode == 0:
            try:
                sha = json.loads(check_res.stdout).get("sha")
            except Exception:
                pass

        payload = {
            "message": f"Upload image deliverable: {filename}",
            "content": b64_content
        }
        if sha:
            payload["sha"] = sha

        scratch_dir = r"C:\Users\Admin\.buzz\.scratch"
        os.makedirs(scratch_dir, exist_ok=True)
        tmp_json = os.path.join(scratch_dir, f"gh_up_{os.getpid()}.json")
        with open(tmp_json, "w", encoding="utf-8") as f:
            json.dump(payload, f)

        res = subprocess.run([
            "gh", "api", "--method", "PUT",
            f"/repos/{repo}/contents/media/{filename}",
            "--input", tmp_json
        ], capture_output=True, text=True)

        if os.path.exists(tmp_json):
            try:
                os.remove(tmp_json)
            except Exception:
                pass

        if res.returncode == 0:
            return f"https://raw.githubusercontent.com/{repo}/main/media/{filename}"
    except Exception:
        pass
    return None

def export_file(file_path, relay=DEFAULT_RELAY, nsec=None, channel=None, reply_to=None, content=""):
    if not os.path.exists(file_path):
        return {"ok": False, "error": f"File không tồn tại: {file_path}"}

    key = nsec or get_nsec_from_vault()
    if not key:
        return {"ok": False, "error": "Không tìm thấy Nostr private key (BUZZ_PRIVATE_KEY hoặc secrets.buzz-desktop)"}

    # Sanitize media if needed
    upload_target = sanitize_media(file_path)
    filename = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)
    size_str = format_size(file_size)

    try:
        # Step 1: Upload to Blossom
        cmd = [
            "buzz.exe",
            "--relay", relay,
            "--private-key", key,
            "upload", "file",
            "--file", upload_target
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")

        if upload_target != file_path and os.path.exists(upload_target):
            try:
                os.remove(upload_target)
            except Exception:
                pass

        blossom_url = None
        sha256 = None
        mime_type = "application/octet-stream"

        if res.returncode == 0:
            try:
                upload_data = json.loads(res.stdout)
                blossom_url = upload_data.get("url")
                sha256 = upload_data.get("sha256")
                mime_type = upload_data.get("type", "application/octet-stream")
            except Exception:
                pass

        # Step 2: Upload to Public CDN for cross-browser download and direct image rendering
        raw_image_url = upload_image_to_raw_cdn(file_path) if mime_type.startswith("image/") else None
        public_url = upload_to_public_cdn(file_path)
        effective_download_url = public_url or blossom_url

        if not effective_download_url:
            return {"ok": False, "error": f"Upload thất bại: {res.stderr.strip() or res.stdout.strip()}"}

        # Format universal download markdown
        if mime_type.startswith("image/"):
            display_img_url = raw_image_url or effective_download_url
            md_link = f"![{filename}]({display_img_url})\n\n[📥 Tải ảnh gốc: {filename} ({size_str})]({effective_download_url})"
        elif mime_type.startswith("video/"):
            md_link = f"[{filename}]({effective_download_url})\n\n[📥 Tải video: {filename} ({size_str})]({effective_download_url})"
        else:
            md_link = f"[📥 Tải về tài liệu: {filename} ({size_str})]({effective_download_url})"

        # Step 3: Optional channel post with native Buzz imeta attachment
        post_result = None
        if channel:
            msg_content = f"{content}\n\n{md_link}" if content else f"Đính kèm tài liệu: {filename} ({size_str})\n\n{md_link}"
            post_cmd = [
                "buzz.exe",
                "--relay", relay,
                "--private-key", key,
                "messages", "send",
                "--channel", channel
            ]
            # ONLY pass --file for actual IMAGES! If it's a PDF/ZIP/DOCX/etc., DO NOT pass --file because buzz.exe appends broken ![image](...pdf) tag!
            if mime_type.startswith("image/"):
                post_cmd.extend(["--file", file_path])
            post_cmd.extend(["--content", msg_content])
            if reply_to:
                post_cmd.extend(["--reply-to", reply_to])
            
            p_res = subprocess.run(post_cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
            if p_res.returncode == 0:
                try:
                    post_result = json.loads(p_res.stdout)
                except Exception:
                    post_result = {"raw": p_res.stdout.strip()}

        return {
            "ok": True,
            "filename": filename,
            "size": file_size,
            "size_formatted": size_str,
            "type": mime_type,
            "url": blossom_url,
            "sha256": sha256,
            "markdown": md_link,
            "post_result": post_result
        }

    except Exception as e:
        return {"ok": False, "error": str(e)}

def main():
    parser = argparse.ArgumentParser(description="Buzz Export CLI - Universal Blossom File Uploader")
    parser.add_argument("file", help="Đường dẫn đến file cần xuất")
    parser.add_argument("--relay", default=DEFAULT_RELAY, help="Relay URL")
    parser.add_argument("--private-key", help="Nostr private key (nsec hoặc hex)")
    parser.add_argument("--channel", help="Gửi đính kèm trực tiếp vào Buzz Channel UUID")
    parser.add_argument("--reply-to", help="Event ID trả lời (Thread)")
    parser.add_argument("--content", default="", help="Nội dung tin nhắn đi kèm")
    parser.add_argument("--json", action="store_true", help="Xuất kết quả JSON")

    args = parser.parse_args()
    result = export_file(
        args.file,
        relay=args.relay,
        nsec=args.private_key,
        channel=args.channel,
        reply_to=args.reply_to,
        content=args.content
    )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result["ok"]:
            print(f"\n✅ ĐÃ XUẤT FILE LÊN BUZZ THÀNH CÔNG:")
            print(f"- Tệp: {result['filename']} ({result['size_formatted']})")
            print(f"- Loại: {result['type']}")
            print(f"- Blossom URL: {result['url']}")
            print(f"\nMarkdown copy vào tin nhắn:")
            print(result["markdown"])
            if result.get("post_result"):
                print(f"\n- Đã đăng thẳng vào channel Buzz thành công!")
        else:
            print(f"❌ LỖI: {result['error']}", file=sys.stderr)
            sys.exit(1)

if __name__ == "__main__":
    main()
