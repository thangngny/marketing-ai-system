#!/usr/bin/env python3
"""
Buzz Multi-Agent Active Dispatch Tool
Enables Marketing Orchestrator and specialist agents to wake up sibling agents via authentic Nostr mentions.
"""

import argparse
import json
import os
import subprocess
import sys
import win32cred

# Ensure UTF-8 output on Windows
sys.stdout.reconfigure(encoding='utf-8')

BUZZ_EXE = r"D:\Buzz\buzz.exe"
MANAGED_AGENTS_PATH = r"C:\Users\Admin\AppData\Roaming\xyz.block.buzz.app\agents\managed-agents.json"
DEFAULT_RELAY = "wss://phamgianam.communities.buzz.xyz"

# Agent Registry: canonical name, pubkey, and common aliases
AGENT_REGISTRY = {
    "Marketing Orchestrator": {
        "pubkey": "9612286f19ecd7692958e7eda8fc449535b3a7076ef45ca17a8bd40ed9ce8e87",
        "aliases": ["orchestrator", "marketing_orchestrator", "marketing orchestrator", "dieu phoi", "assistant", "assistant marketing", "assistant_marketing", "tro ly", "tro ly marketing"]
    },
    "Content Planner": {
        "pubkey": "8f417c9a9e5976b031872b598729051349f49e4f8b34487c81c0415328e0bbdc",
        "aliases": ["content planner", "planner", "content_planner", "ke hoach noi dung"]
    },
    "Creative Studio": {
        "pubkey": "56d445607f66dfdb55cc6630ae0bc9b14bbd2efc89b89432da61b9c3f94e8fdc",
        "aliases": ["creative studio", "creative", "studio", "creative_studio", "sang tao"]
    },
    "Strategy": {
        "pubkey": "62568f1db283a647e7c720faf607295a97357a6ec071ef0e4c663729e1b8bc18",
        "aliases": ["strategy", "chien luoc", "chien_luoc"]
    },
    "Organic & Social": {
        "pubkey": "f0e1d0f7e352eda2a923a0feef4d54febe96fc4299505ffa7215733a1b8d570c",
        "aliases": ["organic & social", "social", "organic", "organic_social", "mang xa hoi"]
    },
    "Paid Media": {
        "pubkey": "0986bbed13eb29118a0c0bcb556387349b9ca602e7abb600e3d33f98c066e516",
        "aliases": ["paid media", "paid", "ads", "paid_media", "quang cao"]
    },
    "SEO & Web": {
        "pubkey": "5a6b7b3846dbcf6e4ef005d37f0a8e55358cc021ed46d51b0f4568afa2c0905b",
        "aliases": ["seo & web", "seo", "web", "seo_web"]
    },
    "Research Intelligence": {
        "pubkey": "e34370d056e62eb48eb3cb95696649ad1ea65e72a648513842e51958bcb97ff8",
        "aliases": ["research intelligence", "research", "intelligence", "nghien cuu"]
    },
    "Sales Enablement": {
        "pubkey": "d3d7d68286381204095d82b9a679a41465a8a905db0fc1a605080cfe70623982",
        "aliases": ["sales enablement", "sales", "sales_enablement"]
    },
    "Analytics & Finance": {
        "pubkey": "7f356c7eadbb1e853a3947cc11d730a14b46bc09af1ff7429d0ab41caaf7cbd3",
        "aliases": ["analytics & finance", "analytics", "finance", "phan tich", "tai chinh"]
    },
    "Knowledge": {
        "pubkey": "fbc48fb951751d9c2e93b741d3348e750ae7038e6b1e6d45f06e50af67dfd868",
        "aliases": ["knowledge", "kien thuc"]
    },
    "CRM & Lifecycle": {
        "pubkey": "4d18dbc5012b45f393094de14c6a4e00c455980068fc7501b9c005df102707d6",
        "aliases": ["crm & lifecycle", "crm", "lifecycle"]
    },
    "Agent Chuẩn hóa & Lọc trùng Data": {
        "pubkey": "d8bc8636ace9cb8b0483be42d8ec78efa6b979a9a3d0365c15d1c9427303674b",
        "aliases": ["data cleaner", "chuan hoa data", "loc trung data"]
    },
    "Agent QA & Chuẩn hóa Zoho": {
        "pubkey": "922fbe242bad87a10abf69ad8918f7ead98da59b98ba9ebd9dfe8da7bdada251",
        "aliases": ["zoho qa", "chuan hoa zoho"]
    },
    "Agent Tra cứu & Xác minh Doanh nghiệp": {
        "pubkey": "0913ce741b5b74b29902654a2e79ee197ee93ba1acedfa50e7d975286c3aa64c",
        "aliases": ["business verifier", "tra cuu doanh nghiep", "xac minh doanh nghiep"]
    },
    "Agent Tìm Contact & Enrichment": {
        "pubkey": "255ead75dbad39dff087ba014bfc3247eaace4a154a29974e85ee3835c78f6df",
        "aliases": ["contact enricher", "enrichment", "tim contact"]
    },
    "Agent Tìm nguồn & Trích xuất Data XNK": {
        "pubkey": "b57b0adb1f7f461be3b474928f9aa536782603e407de0b004b25c0eb153aa51c",
        "aliases": ["xnk extractor", "data xnk", "trich xuat xnk"]
    },
    "Agent Xác định Mã ngành Minh Vân": {
        "pubkey": "38a8192d237d1d6e642b67408e81267a0d8440f4f4b18e3ee193c240337d8798",
        "aliases": ["industry tagger", "ma nganh"]
    }
}

# Channel mappings by name to UUID
CHANNEL_MAP = {
    "00-command": "d46f8fdd-6461-41ae-96d9-c10ab189f275",
    "command": "d46f8fdd-6461-41ae-96d9-c10ab189f275",
    "01-strategy": "f2f333f3-8b98-4a71-9468-9e78ff83ed58",
    "strategy": "f2f333f3-8b98-4a71-9468-9e78ff83ed58",
    "02-content": "3c7bc657-dd4e-42e6-aa33-117f6bd06a84",
    "content": "3c7bc657-dd4e-42e6-aa33-117f6bd06a84",
    "03-campaign": "5648d959-587e-4cb9-b114-e8373086406b",
    "campaign": "5648d959-587e-4cb9-b114-e8373086406b",
    "04-leads": "1ab0ba10-58b8-4319-80d5-30751e6e86a9",
    "leads": "1ab0ba10-58b8-4319-80d5-30751e6e86a9",
    "05-sales": "4b1fb626-2602-4a1e-8d9b-da201d06d6a0",
    "sales": "4b1fb626-2602-4a1e-8d9b-da201d06d6a0",
    "06-kpi-learning": "d6fdc0cd-0583-4308-b4dc-83ff956de80c",
    "kpi": "d6fdc0cd-0583-4308-b4dc-83ff956de80c",
    "test-agents": "d2ae6332-e5a1-4e65-8f56-8a9e15bc47da",
    "test": "d2ae6332-e5a1-4e65-8f56-8a9e15bc47da",
    "general": "d6f20cff-8936-5cc0-8c83-d74246d9712d",
    "tiktok": "df4d4599-891c-445f-aed1-4858b5bbec12",
    "facebook-ads": "fb7c385e-a456-4b5b-aaae-f70c5ee43298",
    "facebook-post": "4f6aca32-956b-43eb-9b72-0640b90c3705",
    "youtube": "e47f97d9-a625-4c19-a622-f204c83708e5",
    "linkedin": "3b06be70-dd0b-493d-ad72-e08c74da6f2d",
    "data": "953808de-d3db-40f1-8cdb-40cd9fcfdc7b",
    "zoho": "90e16062-cd6b-4dd4-9db4-ae8271c5e138",
    "assistant-marketing": "a6399188-f310-4985-a218-35c96209945c",
    "assistant": "a6399188-f310-4985-a218-35c96209945c",
    "assistant marketing": "a6399188-f310-4985-a218-35c96209945c"
}

def resolve_agent(query: str):
    q = query.strip().lower()
    for name, info in AGENT_REGISTRY.items():
        if q == name.lower() or q == info["pubkey"].lower():
            return name, info["pubkey"]
        for alias in info["aliases"]:
            if q == alias.lower():
                return name, info["pubkey"]
    # Partial substring search
    for name, info in AGENT_REGISTRY.items():
        if q in name.lower():
            return name, info["pubkey"]
        for alias in info["aliases"]:
            if q in alias.lower():
                return name, info["pubkey"]
    return None, None

def resolve_channel(channel_str: str) -> str:
    if not channel_str:
        return CHANNEL_MAP["00-command"]
    c_lower = channel_str.strip().lower()
    if c_lower in CHANNEL_MAP:
        return CHANNEL_MAP[c_lower]
    # Check if already a UUID
    if len(channel_str) == 36 and channel_str.count('-') == 4:
        return channel_str
    # Search partial
    for name, cid in CHANNEL_MAP.items():
        if c_lower in name:
            return cid
    return channel_str

def get_credentials(from_agent: str = "Marketing Orchestrator"):
    # First check env vars
    env_key = os.environ.get("BUZZ_PRIVATE_KEY")
    env_tag = os.environ.get("BUZZ_AUTH_TAG")
    env_relay = os.environ.get("BUZZ_RELAY_URL", DEFAULT_RELAY)
    if env_key:
        return env_key, env_tag, env_relay

    # Read from managed-agents.json
    try:
        with open(MANAGED_AGENTS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        sender_name, sender_pubkey = resolve_agent(from_agent)
        for item in data:
            if item.get("pubkey") == sender_pubkey or (sender_name and item.get("name") == sender_name):
                nsec = item.get("private_key_nsec")
                auth_tag = item.get("auth_tag")
                relay = item.get("relay_url") or DEFAULT_RELAY
                if nsec:
                    return nsec, auth_tag, relay
    except Exception:
        pass

    # Read from secrets.buzz-desktop if needed
    try:
        creds = win32cred.CredRead('secrets.buzz-desktop', 1)
        raw = creds['CredentialBlob'].decode('utf-16-le')
        vault = json.loads(raw)
        sender_name, sender_pubkey = resolve_agent(from_agent)
        if sender_pubkey and f"agent:{sender_pubkey}" in vault:
            return vault[f"agent:{sender_pubkey}"], None, DEFAULT_RELAY
        if "identity" in vault:
            return vault["identity"], None, DEFAULT_RELAY
    except Exception:
        pass

    return None, None, DEFAULT_RELAY

def dispatch(to_agent: str, message: str, channel: str = "00-command", from_agent: str = "Marketing Orchestrator", reply_to: str = None):
    target_name, target_pubkey = resolve_agent(to_agent)
    if not target_name:
        return {"status": "error", "message": f"Target agent '{to_agent}' not found in registry."}

    channel_id = resolve_channel(channel)
    private_key, auth_tag, relay = get_credentials(from_agent)

    if not private_key:
        return {"status": "error", "message": f"Could not resolve private key for sender '{from_agent}'."}

    # Format message with @mention
    content = message.strip()
    if not content.startswith(f"@{target_name}"):
        content = f"@{target_name}\n\n{content}"

    cmd = [
        BUZZ_EXE,
        "--relay", relay,
        "--private-key", private_key,
    ]

    if auth_tag:
        cmd.extend(["--auth-tag", auth_tag])

    cmd.extend([
        "messages", "send",
        "--channel", channel_id,
        "--content", content,
        "--mention", target_pubkey
    ])

    if reply_to:
        cmd.extend(["--reply-to", reply_to])

    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")

    if res.returncode == 0:
        try:
            out = json.loads(res.stdout)
            return {
                "status": "success",
                "message": f"Successfully dispatched task to @{target_name}.",
                "target_agent": target_name,
                "target_pubkey": target_pubkey,
                "channel_id": channel_id,
                "event_id": out.get("event_id"),
                "mention_pubkeys": out.get("mention_pubkeys", [target_pubkey])
            }
        except Exception:
            return {
                "status": "success",
                "message": f"Dispatched task to @{target_name}.",
                "raw_output": res.stdout.strip()
            }
    else:
        err = res.stderr.strip()
        # If target is missing from channel, auto-add target via owner and retry once
        if "not channel members" in err:
            try:
                creds = win32cred.CredRead('secrets.buzz-desktop', 1)
                owner_nsec = json.loads(creds['CredentialBlob'].decode('utf-16-le'))['identity']
                add_cmd = [
                    BUZZ_EXE, "--relay", relay, "--private-key", owner_nsec,
                    "channels", "add-member", "--channel", channel_id, "--pubkey", target_pubkey, "--role", "bot"
                ]
                subprocess.run(add_cmd, capture_output=True, text=True)
                # Retry dispatch
                res2 = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
                if res2.returncode == 0:
                    out = json.loads(res2.stdout)
                    return {
                        "status": "success",
                        "message": f"Added to channel and dispatched to @{target_name}.",
                        "target_agent": target_name,
                        "event_id": out.get("event_id")
                    }
            except Exception:
                pass
        return {"status": "error", "message": f"Dispatch failed: {err}"}

def main():
    parser = argparse.ArgumentParser(description="Buzz Multi-Agent Active Dispatch Tool")
    parser.add_argument("--to", required=True, help="Target agent name or alias (e.g. 'Content Planner', 'Strategy')")
    parser.add_argument("--message", required=True, help="The task brief or instruction for the specialist")
    parser.add_argument("--channel", default="00-command", help="Channel name or UUID (default: '00-command')")
    parser.add_argument("--from-agent", default="Marketing Orchestrator", help="Sending agent identity (default: 'Marketing Orchestrator')")
    parser.add_argument("--reply-to", default=None, help="Event ID to reply to (optional thread linking)")
    parser.add_argument("--json", action="store_true", help="Output JSON only")

    args = parser.parse_args()
    result = dispatch(args.to, args.message, args.channel, args.from_agent, args.reply_to)
    
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("status") != "success":
        sys.exit(1)

if __name__ == "__main__":
    main()
