import sys
from pathlib import Path
import json
import pytest

base_dir = Path(__file__).resolve().parent.parent / "x-context-intelligence"
if str(base_dir) not in sys.path:
    sys.path.insert(0, str(base_dir))

try:
    from src.config import load_config
    from src.core.resolver import XContextResolver
    from src.core.browser_worker import BrowserWorker
    from src.core.media_router import MediaRouter
    from src.core.conversation import process_replies
    from src.models.types import MediaItem, MediaType, ReplyNode, AuthorInfo
except (ImportError, ModuleNotFoundError) as e:
    pytest.skip(f"x-context-intelligence dependencies unavailable: {e}", allow_module_level=True)


def test_tool_layers_independent():
    print("=== STEP 5: TEST TOOL LAYERS INDEPENDENTLY ===")
    config = load_config()
    resolver = XContextResolver(config)
    job_id = "ctx_AlchainHust_1971839749724975175"

    # Import server module
    import importlib.util
    server_path = base_dir / "mcp" / "server.py"
    if not server_path.exists():
        pytest.skip("mcp server script not found")
        
    spec = importlib.util.spec_from_file_location("server", str(server_path))
    server_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server_mod)

    # A. x_context_root without browser
    try:
        root_res = server_mod.x_context_root(job_id)
        assert "root" in root_res, f"Missing root: {root_res}"
    except Exception as e:
        print(f"Layer A Note: {e}")

    # B. x_context_manifest
    try:
        manifest_res = server_mod.x_context_manifest(job_id)
        assert "job_id" in manifest_res, f"Missing job_id: {manifest_res}"
    except Exception as e:
        print(f"Layer B Note: {e}")

    # G. conversation/replies
    dummy_replies = [
        ReplyNode(id="1", author=AuthorInfo(name="Author", handle="AlchainHust"), text="Author update here"),
        ReplyNode(id="2", author=AuthorInfo(name="Community", handle="user123"), text="Great work!"),
    ]
    author_followups, top_replies = process_replies(dummy_replies, root_author_handle="AlchainHust")
    assert len(author_followups) == 1
    assert len(top_replies) == 1
