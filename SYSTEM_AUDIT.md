# System Audit

Audit time: 2026-09-19 (Asia/Saigon)  
Audit mode: read-only until this report was created  
Target host observed: `DESKTOP-OPT3IJ0`

## Executive finding

The machine available to this implementation is a Windows 10 workstation, not the hinted Ubuntu workstation. WSL is present only as the legacy Windows component and has no installed distribution. No `Agent-C-level` checkout was found on `C:`, `D:`, or `E:` within five directory levels.

Buzz Desktop and Hermes Agent are already installed. Hermes 0.21.3 includes the supported native Buzz gateway plugin, but that plugin is not configured. Hermes has no working inference-provider authentication on this host. Buzz has an existing user workspace and active built-in/Codex agents, but the prepared seven-member Marketing Ops team snapshot has not been imported. The Hermes installation repository has unrelated local changes and must not be edited for this project.

## Machine

| COMPONENT | FOUND? | VERSION | PATH | RUNNING? | CONFIGURED? | SAFE_TO_REUSE? | ACTION_REQUIRED | NOTES |
|---|---:|---|---|---:|---:|---:|---|---|
| Host OS | Yes | Windows 10 Home Single Language 10.0.19045 | system | Yes | Yes | Yes | Use Windows-native operational scripts | Requested Ubuntu 24.04 was not found |
| WSL | Component only | legacy/inbox CLI | `C:\Windows\System32\wsl.exe` | No | No distro | No | Do not install without owner decision | `wsl -l -v` exposes no distribution; `--version` unsupported |
| Kernel/build | Yes | NT 10.0.19045 | system | Yes | Yes | Yes | None | x64 |
| CPU | Yes | Intel Core i5-8265U | system | Yes | Yes | Yes | None | 4 cores / 8 logical CPUs |
| RAM | Yes | 12.68 GB physical | system | Yes | Yes | Yes | Monitor during local services | About 3.9 GB free at audit time |
| Disk C: | Yes | NTFS | `C:\` | Yes | Yes | Yes | None | 165.3 GB free / 249.4 GB |
| Disk D: | Yes | NTFS | `D:\` | Yes | Yes | Yes | None | 159.7 GB free / 160.0 GB; Buzz installed here |
| Disk E: | Yes | NTFS | `E:\` | Yes | Yes | Yes | None | 837.2 GB free / 838.9 GB |

## Developer and runtime tools

| COMPONENT | FOUND? | VERSION | PATH | RUNNING? | CONFIGURED? | SAFE_TO_REUSE? | ACTION_REQUIRED | NOTES |
|---|---:|---|---|---:|---:|---:|---|---|
| Git | Yes | 2.54.0.windows.1 | `C:\Users\Admin\AppData\Local\hermes\git\cmd\git.exe` | N/A | Yes | Yes | None | Bundled with Hermes |
| curl | Yes | 8.13.0 | `C:\Windows\System32\curl.exe` | N/A | Yes | Yes | None | Schannel TLS |
| wget | No | — | — | No | No | N/A | Not required | Use curl |
| jq | No | — | — | No | No | N/A | Avoid dependency | PowerShell/Python can parse JSON |
| make | No | — | — | No | No | N/A | Not required for MVP | — |
| just | No | — | — | No | No | N/A | Not required | — |
| Docker / Compose | No | — | — | No | No | N/A | Avoid for MVP | No containers present |
| Podman | No | — | — | No | No | N/A | Not required | — |
| Python | Yes, isolated | 3.11.16 | `C:\Users\Admin\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe` | No | Yes | Limited | Create a project-local environment | Windows Store `python.exe` stubs are also on PATH |
| pip | Yes, isolated | via Hermes venv | Hermes venv | No | Yes | No for project writes | Use `uv` project environment | Do not add packages to Hermes venv |
| pipx | No | — | — | No | No | N/A | Not required | — |
| uv / uvx | Yes | 0.12.17 | `C:\Users\Admin\AppData\Local\hermes\bin` | N/A | Yes | Yes | Pin project dependencies | — |
| Node | Yes | 24.21.0 | `C:\Users\Admin\AppData\Local\Programs\node-v24.21.0-win-x64` | Several Codex helper processes | Yes | Yes | Do not upgrade globally | — |
| npm / npx | Yes | 11.19.0 | Node installation | N/A | Yes | Yes | None | — |
| pnpm | No | — | — | No | No | N/A | Not required | — |
| corepack | Yes | 0.36.0 | Node installation | N/A | Yes | Yes | None | — |
| Rust / cargo / rustup | No | — | — | No | No | N/A | Do not install; Buzz binaries already exist | — |
| SQLite CLI | No | — | — | No | No | N/A | Use Python stdlib SQLite | No new database service required |
| PostgreSQL client | No | — | — | No | No | N/A | Not required | SQLite chosen for staging |
| systemd --user | No | N/A on Windows | — | No | No | N/A | Use Windows Scheduled Task only after smoke pass | No relevant scheduled task currently exists |

## AI and orchestration tooling

| COMPONENT | FOUND? | VERSION | PATH | RUNNING? | CONFIGURED? | SAFE_TO_REUSE? | ACTION_REQUIRED | NOTES |
|---|---:|---|---|---:|---:|---:|---|---|
| Hermes Agent | Yes | 0.21.3 (2026.9.14), upstream `debfc742` | `C:\Users\Admin\AppData\Local\hermes\bin\hermes.exe` | Gateway stopped | Partial | Yes as installed binary | Create isolated `marketing_orchestrator` profile | Do not edit installation checkout |
| Hermes source/install repo | Yes | `debfc742`, branch `main` | `C:\Users\Admin\AppData\Local\hermes\hermes-agent` | No editor target detected | Dirty | Read-only only | Preserve local modifications | Modified: `package-lock.json` and two Chinese docs |
| Extracted Hermes source | Yes | apparent later snapshot | `C:\Users\Admin\hermes-agent-main` | No | No Git metadata | Read-only reference | Do not use as project repo | Created/updated 2026-09-19 |
| Hermes home | Yes | config schema v current install | `C:\Users\Admin\AppData\Local\hermes` | No gateway | Default profile only | Preserve | Back up before profile/config changes | `HERMES_HOME` points here |
| Hermes provider | No usable auth | Config says `anthropic/claude-opus-4.6`, provider `auto` | Hermes config | No | No | No | Owner must authenticate a supported provider | Hermes status reports all providers unavailable; no Vertex config found |
| Hermes profiles | Yes | default only | profile registry | Gateway stopped | default only | Preserve | Add isolated marketing profile | No existing profiles will be migrated |
| Hermes native Buzz gateway | Yes | bundled plugin in 0.21.3 | Hermes bundled `buzz` platform plugin | No | No | Yes | Configure dedicated identity/channel and allowlist | Native path is supported and preferred |
| Hermes MCP | Yes | CLI present | `hermes mcp` | No | No marketing server | Yes | Register project-local integration server | No need to modify Hermes core |
| Hermes ACP | Yes | 0.21.3 launcher | `C:\Users\Admin\AppData\Local\hermes\bin\hermes-acp.exe` | No | Import check not yet run | Optional | Retain as fallback only | Native Buzz gateway remains primary |
| Codex CLI | Yes | 0.155.1 | OpenAI Codex installation | Multiple Codex processes | Yes for Codex app | Do not change | Avoid their active workspaces | No active Codex process command line referenced the target directories |
| Gemini / Vertex | Gemini local folders only | unknown | `C:\Users\Admin\.gemini` | No relevant process | No gcloud/Vertex env detected | No | Leave untouched | No `gcloud`, no Google/Vertex env vars, no proof of working Vertex auth |
| `hermes-new` wrapper | No | — | — | No | No | N/A | Not needed | No alias/wrapper found |

## Buzz

| COMPONENT | FOUND? | VERSION | PATH | RUNNING? | CONFIGURED? | SAFE_TO_REUSE? | ACTION_REQUIRED | NOTES |
|---|---:|---|---|---:|---:|---:|---|---|
| Buzz Desktop | Yes | 0.5.23 | `D:\Buzz\buzz-desktop.exe` | No at audit time | Yes, existing user workspace | Yes | Start only for UI acceptance | Existing workspace relay is configured |
| Buzz CLI binary | Yes | bundled with 0.5.23 | `D:\Buzz\buzz.exe` | No | CLI help produced no console output | Conditional | Validate real JSON command path through Hermes plugin | Not on PATH |
| buzz-acp | Yes | bundled with 0.5.23 | `D:\Buzz\buzz-acp.exe` | No | No | Optional fallback | Do not make mandatory | — |
| buzz-agent | Yes | bundled with 0.5.23 | `D:\Buzz\buzz-agent.exe` | No | Existing managed agents | Yes | Preserve | — |
| Buzz relay/workspace | Yes | hosted community | `wss://phamgianam.communities.buzz.xyz` | Remote | Existing desktop identity | Yes | Need dedicated Hermes identity and channel membership | Do not disclose private identity material |
| Buzz managed agents | Yes | 8 entries | Buzz app data | Not running at audit time | Built-ins + Codex | Preserve | Do not overwrite | Current team registry contains only the Welcome Team |
| Marketing Ops Buzz snapshot | Yes | snapshot format v1 | `C:\Users\Admin\buzz-marketing\marketing-ops.team.json` | No | Prepared, not imported | Reuse as reference | Do not import blindly | Seven agents: command, strategy, content, campaign, leads, sales, KPI |

## Repositories and workspaces

| COMPONENT | FOUND? | VERSION | PATH | RUNNING? | CONFIGURED? | SAFE_TO_REUSE? | ACTION_REQUIRED | NOTES |
|---|---:|---|---|---:|---:|---:|---|---|
| Agent-C-level | No | — | — | No | No | N/A | Use independent project | No matching directory found in scoped drive scan |
| Existing marketing workspace | Yes | not a Git repo | `C:\Users\Admin\buzz-marketing` | No editor target detected | Partial prompts/team snapshot | Read-only/reference | Preserve unchanged | Has its own `AGENTS.md`; no connectors or operational layer |
| Existing marketing Hermes skills | Yes | seven skill directories | `C:\Users\Admin\Documents\Codex\2026-09-17\tta\work\hermes-marketing-skills` | No | Prepared | Reuse by copy/reference after review | Validate against current Hermes skill contract | No Git metadata found |
| New isolated implementation | Yes | new, initially empty | `C:\Users\Admin\marketing-ai-system` | No | No | Yes | Implement here | Created only after read-only audit |

## Processes, ports, services

- Active AI tooling: multiple Codex/Code Mode/Node helper processes and one `agy.exe` process. Sanitized command-line matching found none targeting `buzz-marketing`, `hermes-agent-main`, or the installed Hermes checkout.
- Buzz Desktop, Hermes gateway, Docker, PostgreSQL, Python project services, and marketing services were not running at audit time.
- No relevant Windows service, startup entry, or Scheduled Task for Hermes/Buzz/marketing was found.
- No project service port was listening. Observed listeners were Windows services plus the local `agy.exe` listener on `127.0.0.1:50380-50381` and an unrelated loopback listener on `[::1]:42050`.
- No container runtime is installed, so there are no Docker/Podman containers to reuse or collide with.

## Configuration and credential presence

Secrets were not printed. The audit inspected only key names, configured/missing state, and non-secret settings.

| AREA | RESULT |
|---|---|
| Hermes `.env` | Exists, but inspected named entries are operational defaults; no provider/API credentials reported by `hermes status` |
| Hermes default config | Exists; local terminal backend; streaming disabled; shared telemetry disabled; no enabled custom plugins |
| Hermes Buzz config | Missing |
| Hermes inference auth | Missing/unusable |
| Vertex AI | Not detected |
| Buzz desktop identity | Exists implicitly through the configured desktop workspace; secret material was not read or exported |
| Zoho/M365/Apollo/LinkedIn/YouTube/Meta/Google Ads | No project credentials detected or assumed |

## Safety decision

It is safe to continue with reversible, user-level work in `C:\Users\Admin\marketing-ai-system` and to reuse the installed Hermes/Buzz executables without editing their installation directories.

Guardrails for later phases:

1. Do not modify or clean the dirty Hermes installation worktree.
2. Back up Hermes state before creating the marketing profile or changing gateway configuration.
3. Keep all external connectors in deterministic mock mode until explicit credentials exist.
4. Do not import/overwrite the existing Buzz marketing snapshot automatically.
5. Do not enable autostart until the native Buzz round trip and project smoke tests pass.
6. Treat live Buzz↔Hermes verification as blocked until a dedicated Buzz identity/channel membership and a working Hermes inference provider are available.

