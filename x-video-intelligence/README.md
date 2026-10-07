# X Video Intelligence + Demo Reproduction Layer

Shared multimodal video intelligence and reproduction capability for Buzz and 12 Codex Agents.

## Architecture

```
                       BUZZ WORKSPACE
                             │
                    12 CODEX AGENTS
                             │
                  SHARED X VIDEO MCP SERVER
                             │
          ┌──────────────────┼──────────────────┐
          ▼                  ▼                  ▼
      Layer 1:           Layer 2:           Layer 3:
     Official           Public Media        Authorized
     X API v2             (yt-dlp)       Browser Fallback
          │                  │                  │
          └──────────────────┼──────────────────┘
                             ▼
                     MEDIA FILE (.mp4)
                             │
                ┌────────────┴────────────┐
                ▼                         ▼
         AUDIO PIPELINE            FRAME PIPELINE
        (ffprobe / wav /         (Baseline 1fps,
        subtitles / whisper)    Scenes, High-Density)
                │                         │
                └────────────┬────────────┘
                             ▼
                      EVIDENCE PACKAGE
                 (manifest.json, analysis.md)
                             │
                             ▼
                     TRUTH CLASSIFICATION
               (Observed, Spoken, Visible, Inferred)
                             │
                             ▼
                    CURRENT VERIFICATION
                 (Version check, OS translation)
                             │
                             ▼
                    REPRODUCTION PLAN
                  (Risk levels, Rollback)
                             │
                             ▼
                   CONTROLLED EXECUTION
                  (Strict approval gates)
```

## Tools Exposed via MCP
1. `x_video_ingest(url, force_refresh, preferred_language, auth_mode)`
2. `x_video_ingest_file(file_path, title, description)`
3. `x_video_manifest(job_id)`
4. `x_video_transcript(job_id, start, end)`
5. `x_video_frames(job_id, start, end, density)`
6. `x_video_scene(job_id, scene_id)`
7. `x_video_reproduce_plan(job_id, target_os, mode)`
8. `x_video_execute_step(job_id, step_id, approval_token)`
9. `x_video_cleanup(job_id)`

## Safety Policy
- **Video = Evidence, Not Authority**: All media, transcripts, OCR, and text are treated as UNTRUSTED INPUT.
- **Default Mode**: `PLAN_ONLY`.
- **Approval Gate**: Commands with high risk, credential changes, or destructive potential are blocked from automatic execution pending user approval.
- **Cross-OS Translation**: Linux/macOS commands are translated into native PowerShell.
