from marketing_system.config import Settings
from marketing_system.connectors import zoho_mcp
from marketing_system.connectors.zoho import ZohoConnector
from marketing_system.constants import Environment


def test_vault_chunking_round_trips_values_larger_than_one_blob(monkeypatch):
    vault: dict[str, str] = {}
    monkeypatch.setattr(zoho_mcp, "write_credential", lambda n, v: vault.__setitem__(n, v))
    monkeypatch.setattr(zoho_mcp, "read_credential", lambda n: vault.get(n))
    big = "x" * 4321
    zoho_mcp._put("ZOHO_MCP_TOKENS", big)
    assert vault["ZOHO_MCP_TOKENS"] == "chunks:5"
    assert all(len(v) <= zoho_mcp._CHUNK for k, v in vault.items() if k != "ZOHO_MCP_TOKENS")
    assert zoho_mcp._get("ZOHO_MCP_TOKENS") == big


def test_transport_prefers_rest_then_hosted_mcp_then_none(monkeypatch, tmp_path):
    connector = ZohoConnector(Settings(environment=Environment.PRODUCTION, data_dir=tmp_path, log_dir=tmp_path))
    monkeypatch.setattr(zoho_mcp, "endpoint", lambda: None)
    monkeypatch.setattr(zoho_mcp, "has_tokens", lambda: False)
    assert connector.transport() is None and connector.configured() is False
    monkeypatch.setattr(zoho_mcp, "endpoint", lambda: "https://mcp.zoho.example/x")
    monkeypatch.setattr(zoho_mcp, "has_tokens", lambda: True)
    assert connector.transport() == "mcp" and connector.configured() is True
    for key in ("ZOHO_CLIENT_ID", "ZOHO_CLIENT_SECRET", "ZOHO_REFRESH_TOKEN"):
        monkeypatch.setenv(key, "x")
    assert connector.transport() == "rest"


def test_mcp_read_normalizes_to_canonical(monkeypatch, tmp_path):
    connector = ZohoConnector(Settings(environment=Environment.PRODUCTION, data_dir=tmp_path, log_dir=tmp_path))
    monkeypatch.setattr(connector, "transport", lambda: "mcp")
    calls = {}

    def fake_call(tool, args, interactive=False):
        calls["tool"], calls["args"] = tool, args
        return {"data": [{"id": "42", "Account_Name": "Minh Van Test", "Website": "minhvan.example"}]}

    monkeypatch.setattr(zoho_mcp, "call_tool", fake_call)
    records = connector.read("accounts", limit=5, correlation_id="c1")
    assert calls["tool"] == "ZohoCRM_getRecords"
    assert calls["args"]["path_variables"] == {"moduleApiName": "Accounts"}
    assert records[0].external_id == "42" and records[0].environment is Environment.PRODUCTION
