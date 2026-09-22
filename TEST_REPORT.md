# Test Report

Date: 2026-09-19  
Mode: `mock` + `SAFE_DRY_RUN`

## Result

`LIVE_E2E_PASS` for the Buzz front door and mock business workflows. No live business connector was called.

## Automated suite

```powershell
.\scripts\smoke-test.ps1
```

- `PASS`: 33 pytest tests.
- `PASS_MOCK`: 4 local acceptance executions.
- `SKIPPED_NEEDS_AUTH`: 8 live connector tests.
- `FAIL`: 0.

## Live Buzz evidence

| TEST | RESULT | REQUEST EVENT | REPLY EVENT | TOOL / CORRELATION |
|---|---|---|---|---|
| Provider exact reply | PASS | local profile prompt | `HERMES_MARKETING_OK` | OpenAI Codex OAuth / `gpt-5.6-sol` |
| Buzz transport | PASS | `32bc83b321eed85b6e9320ddc105517d58d454c89836860603440beeb11b8ce5` | `632ad7261a81fb067e9fa66517f23d74d6fbeece7bd1532aa69fd5836a34e4f3` (`BUZZ_OK`) | Hermes native Buzz gateway |
| System status | PASS_MOCK | `7e8b4687ce5665553b51501ffd2c4af96726c4902d0804a203e6c14fbdde83d8` | `50caa285b17063f33e3a88384cb7b37f457bbfcb87b7f0db8c165466d9d3273f` | `marketing_handle_request` / `930ab401-25d6-43d7-a58e-641680d8b66f` |
| Three mock leads | PASS_MOCK | `4c7ff41a49554e92ef0e4075e2ec4054aabc109ea8c8d709b16b6af75f362478` | `67dc96c6f61c3e49c5b3b4d1c9a04f2ae696190df98021acb5c9a4f0a0ffdde7` | `03_account_intelligence`, `apollo+zoho` / `24b3e50b-f1c5-4c32-8035-8ba4c352dd99` |
| LinkedIn draft | PASS_MOCK | `41255cc573232a0191ebc0fdff8ceb4602b70fc5fead1a84f5922d4e8cacfa9b` | `64c464e50a4b78aaf2e43d247d1a69d845e799dd6a8ea2f940bb5ab1941b48e2` | `04_content`, `linkedin` / `cf987ee6-b9d9-4274-b2e2-b0ee3f3d01f1` |
| Campaign safety | PASS_MOCK | `403cf289482689d77c6fbe0ffffa619048a83026eceb95b9372ef778c798b7ad` | `5af7cba8194232c73a4357f642497404cc4898e3a94600d7b12c29c29382529d` | `01_strategy+07_campaign`, `meta_ads/google_ads` / `2cc533ab-ec06-4c51-abf9-e1aa4856cb08` |
| Multi-agent routing after fix | PASS_MOCK | `e910f5d25c36d5a89eb604b142b7f5e1a63070bd71f362a5c52daee51081abf3` | `3cb9f626a92442a8588fbd02d8c734ad9cafe6e2d491384ba49bf0f0515d8bb4` | `02_market_intelligence+01_strategy+07_campaign+04_content` / `c182b1e3-6c38-4925-82f8-875cb8183c89` |
| Status after restart | PASS_MOCK | `c38f98b681be3ec7c2741a50941907a6d6d74ae343384f204f4fcf232c01cadc` | `6299285bb51710d9a24cd1754481ba29c38743c3caec4bcdebe0621976958f27` | `marketing_handle_request` / `35cbb15c-5d93-4e02-b72e-36ecddfdf27c` |
| Clean final status | PASS_MOCK | `3cdc1cce9c75e2ef941061f4d739da5dd2a4cd4f5384b34eabd154fa0afcc1fc` | `0e9b85fa7c328ee5aa3a933d196923acb894f60dfcb32bfa1e59d83c39131dc0` | no reasoning noise / `7851b518-dda4-43c8-bef2-2dcae5852c16` |

The leads correlation has exactly three rows in `canonical_records`, all in the mock environment and identified as synthetic. Relay events, gateway logs, integration JSONL, and SQLite evidence were cross-checked.

## Negative tests

- Unauthorized channel member: PASS; relay accepted event `6560fbee55190590bc23886f1f38c67445755c7ba8fa2c5f1140a3de0cf4bdd6`, gateway allowlist produced zero Marketing Orchestrator replies.
- Malformed `???` request: PASS; controlled reply event `5f4140c07fd8c661dc2a22ea145f2a3a8383a14c8c52ffcebaf74fba743844c7`, no crash.
- Unavailable connectors: PASS_MOCK; exact `NEEDS_AUTH`, `NEEDS_ACCESS`, and `CONFIG_REQUIRED` states returned.
- External paid write: PASS_MOCK; no Meta call, launch, budget mutation, or spend.
- Duplicate event: PASS; the installed Hermes Buzz adapter dispatched the same event ID once across two deliveries.

## Restart and autostart

- Graceful stop: PASS; no orphan gateway or MCP process.
- Restart and Buzz reconnect: PASS.
- Start twice: PASS; no duplicate instance.
- User-level autostart: INSTALLED and ENABLED through Hermes' Windows Startup-folder fallback (no administrator approval used).

## External side effects

- Emails sent: 0.
- Posts published: 0.
- Ad campaigns launched/modified: 0.
- Money spent: 0.
- Live CRM records created/updated/deleted: 0.
- Live business connector probes: 0.

## Phase 2 re-verification — 2026-09-22

- `PASS`: 38 pytest tests; 8 live-account tests skipped pending OAuth/API credentials.
- `PASS`: Hermes `marketing` profile provider returned the exact expected response using OpenAI Codex OAuth / `gpt-5.6-sol`.
- `PASS`: the live Buzz relay returned 26 recent events; all seven cited Phase 1 reply event IDs were present and matched their expected markers.
- `PASS`: controlled Hermes gateway stop/start completed cleanly; `doctor.ps1` then reported `Hermes - Buzz: OK - gateway live`.
- `PASS`: website `https://minhvanlogistics.com` returned HTTP 200 through the connector and was classified `CONNECTED` only after the live probe.
- `PASS`: one non-synthetic website `SourceReference` was normalized and staged in the `production` namespace. Existing synthetic leads remain isolated in `mock`.
- `PASS`: connector credentials now resolve from Windows Credential Manager; no business secret was added to Git, SQLite, logs, screenshots, or command-line arguments.
- `PASS`: Meta and YouTube probes were hardened so access tokens/API keys are not placed in query strings, and INFO-level HTTP request logging is suppressed.
- `BLOCKED_OWNER_MFA`: Zoho API Console re-verification and Microsoft Entra portal sign-in.
- `BLOCKED_OWNER_TERMS/ACCESS`: YouTube API enablement terms and LinkedIn Page/app association.
