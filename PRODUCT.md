# CommentCut Studio
<!-- impeccable:product-schema 1 -->
## Platform
desktop (Windows standalone Chromium `--app` window + portable EXE)
## Stack
Local Python FastAPI, plain HTML/CSS/JavaScript, Pillow, Playwright, and FFmpeg. No frontend build step or cloud account required beyond ElevenLabs TTS.
## Users
Vietnamese creators producing high-volume narrated vertical videos from large batches of TikTok and Threads URLs.
## Product Purpose
Import tens or hundreds of public TikTok/Threads URLs (or `.txt` lists), automatically capture real post/comment cards, split into multi-part scripts, synthesize multi-voice ElevenLabs narration, insert paired memes/sounds, and render downloadable MP4s in bulk.
## Capabilities and Constraints
Unified bulk production pipeline; persistent preset configuration; live batch queue with dynamic URL appending, 1-click retry for failed URLs, and 1-click bulk re-render for crawled posts; dedicated ElevenLabs multi-voice pool with SHA-256 audio caching; local media library (`Vid_nen`, `img_meme`, `mp3_meme`) with meme-pair diagnostics and native Windows Explorer folder shortcuts. Public crawling is best effort and never substitutes reconstructed text cards when capture fails.
## Product Principles
Capture actual rendered post/comment cards with native avatars and reaction counts. Keep API credentials strictly server-side (`data/settings.json`). Eliminate single-item manual friction in favor of automated bulk throughput, clear preflight diagnostics, and instant recovery actions.
