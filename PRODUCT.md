# CommentCut
<!-- impeccable:product-schema 1 -->
## Platform
web
## Stack
Delegated by the user: local Python FastAPI, plain HTML/CSS/JavaScript, Pillow and FFmpeg. No frontend build or cloud account required.
## Users
Vietnamese creators turning TikTok/Threads posts and comments into narrated vertical videos.
## Product Purpose
Import a public source, review and edit comments, assign memes and sounds, render downloadable MP4 with reusable background footage.
## Capabilities and Constraints
Local media library; free online Vietnamese TTS; optional ElevenLabs and Vbee credentials; real post/comment screenshot scenes; sequential memes after introduction and between comments; persistent projects and rendering jobs. Public crawling is best effort and explicitly partial, never claims all comments. Manual JSON/text import remains available. User supplies gameplay and licensed meme assets. No automatic publishing.
## Evidence on Hand
Reference https://www.youtube.com/shorts/h-t9ggZKy-A opened in Chrome: vertical gameplay, white conversation image above center, yellow creator credit. Exact audio and frame-by-frame timing have not been extracted. Demo assets are original procedural placeholders, not the reference gameplay.
## Product Principles
Public-source collection captures actual rendered comment cards and stores their text separately for speech. Preserve native avatars and reaction counts in the captured pixels. Never substitute reconstructed comment images when capture fails.
Review before rendering. Preserve full comment text. Report crawl limits. Keep provider credentials server-side. Prefer native tools.
