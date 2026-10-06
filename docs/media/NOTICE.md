# Media provenance and third-party notices

The video, GIF, poster, fictional screen copy, and `src/frameforge.svg` were created for vid2idea. Original project material follows the repository's [MIT license](../../LICENSE). The diagram and mobile fallback, when present in `docs/assets/`, are original project graphics too. FrameForge is fictional; all addresses use reserved example.com names. There are no real Discord messages, Notion records, processed source videos, borrowed screenshots, or photographed assets in the media.

## Hyperframes

Copyright 2026 HeyGen, Inc. Licensed under Apache License 2.0; the complete license is in [hyperframes-APACHE-2.0.txt](licenses/hyperframes-APACHE-2.0.txt).

The original media adapted Hyperframes `grid-card-assemble` and `titlecard-lockup` primitives. The revised `src/story.html` retains the explicit short-slide/opacity reveal technique and replaces the independent scenes with one persistent layout, bounded link travel and document scrolling. The wordmark animation and scene cuts were removed. Original layout, copy, palette, artwork and timing are specific to this project. Unmodified catalog components are not shipped. Sources: [Hyperframes repository](https://github.com/heygen-com/hyperframes) and its [registry](https://github.com/heygen-com/hyperframes/tree/main/registry).

Hyperframes CLI 0.8.106 remains the pinned rendering dependency. The revision uses its reviewed animation/core guidance and the existing GSAP transform adapter; no extra animation runtime or stock app scene is required.

## Fonts

- Manrope: Copyright 2019 The Manrope Project Authors. `@fontsource-variable/manrope` 5.3.0, unmodified Latin variable WOFF2. [Complete SIL Open Font License 1.1](licenses/manrope-OFL.txt).
- JetBrains Mono: Copyright 2020 The JetBrains Mono Project Authors. `@fontsource-variable/jetbrains-mono` 5.2.8, unmodified Latin variable WOFF2. [Complete SIL Open Font License 1.1](licenses/jetbrains-mono-OFL.txt).

The preparation script copies only these two font files into each temporary self-contained project. Font license text is preserved here; generated videos do not redistribute the font binaries.

## GSAP

GSAP 3.14.2 is a pinned development dependency, used to author a fixed video timeline. Its original copyright/license header is retained when its runtime is copied into temporary render projects. GSAP is subject to its own [Standard License](https://gsap.com/community/standard-license/), effective 2025-04-30, last modified 2025-05-30, reviewed 2026-10-05. It is not relicensed under this repository's MIT license. No GSAP runtime binary is committed in these sources.

## Audio and external assets

Both exports intentionally contain no audio: no narration, music, or sound effects. Silence fits README autoplay and keeps the longer demo consistent. Brag's bundled music was not copied because rights to publicly redistribute it in an open-source repository were not established. All rendered assets load locally; the compositions make no runtime network requests.
