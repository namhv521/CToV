# CommentCut Implementation Plan

**Goal:** Local link-to-comment-video studio with editable scenes and real MP4 exports.
**Architecture:** FastAPI + file storage, bounded Playwright collection, provider TTS, Pillow cards, sequential FFmpeg jobs, buildless frontend.
**Spec:** docs/design.md

- [x] Implement models/storage and local API with validated IDs, URLs and uploads.
- [x] Implement source extraction with fixtures, public browser collection and manual imports.
- [x] Implement free/ElevenLabs/Vbee speech and media pipeline with cancellation and timeline manifest; paid integrations need account validation.
- [x] Implement responsive editing desk, asset uploads, save/open, provider settings, render progress/download.
- [x] Run API tests, real speech/render smoke, inspect desktop/narrow layout, package clean source and runnable demo. See verification.md for limits.
