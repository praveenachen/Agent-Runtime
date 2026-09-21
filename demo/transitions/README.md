# Demo transition clips

Three silent 1920×1080, 30 fps, four-second MP4 transitions styled to match the Agent Runtime dashboard.

## Sequence

1. Normal Execution — Summarize Text
2. Retry & Recovery — Extract Structured Data
3. Idempotency Test — Classify Message

Titles and subtitles live in `manifest.json`. After editing them, regenerate every clip from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\demo\transitions\render.ps1
```

The renderer uses Docker, an FFmpeg container, and the local Segoe UI font files. Clips are silent so narration and music can be mixed cleanly in the final edit.
