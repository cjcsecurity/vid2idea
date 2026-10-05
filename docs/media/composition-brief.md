# Hyperframes composition brief: vid2idea

Build one local, self-contained, deterministic HTML/CSS/GSAP composition for the 22-second silent demo and a matching 9-second README loop. Delivery files live in `docs/assets/`; reproducible sources live here. Use the complete storyboard in `brag-plan.md`.

## Source contract

Read only public `README.md`, `examples/brief.md`, `docs/architecture.md`, and `collector/src/vid2idea/notion_content.py`. This collector has no web dashboard. Depict a clearly labeled simulated Discord message and native Notion blocks. Use fictional FrameForge and reserved example.com URLs. Do not run the collector or access real Discord/Notion data.

The resource heading, link, and summary precede use cases. The research answer in the sample is **inconclusive**, with no fabricated citation. Show opened-source research as a collector capability, not as a result produced for fictional FrameForge. A synthetic source image is an original SVG and is labeled as an illustration.

## Visual contract

Landscape, large crisp type, ink process panel against warm paper result. Palette: ink `#17252b`, paper `#f4f0e7`, coral `#b74331`, lime `#d4e897`, muted ink `#56655f`, rule `#d8d7cb`. Use local Manrope and JetBrains Mono WOFF2 assets. Flat solids, carefully placed structural rules, original screen/crop illustration, generous breathing space. Avoid neon SaaS, glow, abstract filler, unsupported metrics, or tiny UI text.

Scene timings: 0–4 hook and Discord input; 4–9 local evidence and research capability; 9–18 illustrated resource-first Notion result; 18–22 retained link/result closing. Motion should track the actual user flow. Fast entrances plus long settled holds; deterministic single paused timeline; explicit from/to poses on inner scene elements.

## Runtime and output

- Hyperframes 0.8.106, GSAP 3.14.2; local dependencies only.
- Demo: `docs/assets/vid2idea-demo.mp4`, 1600×900, 30fps, 22s, silent.
- README preview: `docs/assets/vid2idea-preview.gif`, 960×540, 8fps, 9s, goal ≤3MB.
- Poster: `docs/assets/vid2idea-poster.jpg`, 1600×900, goal ≤250KB. Use the fully settled demo brief at 11.5 seconds as the poster and demo frame zero.
- Optional static diagram: original `docs/assets/pipeline.svg`.
- Keep caches, build bundles, rendered proof snapshots, and logs outside tracked source.
- No narration, music, or SFX. Silence is intentional; bundled music redistribution license is unverified, so no audio is copied.

## Acceptance

Run lint after first construction. Final `hyperframes check` must report zero errors, with nonzero layout and contrast checks. Inspect hook, evidence scene, resource-first result, lower brief sections, final hold, and loop endpoints as snapshots. Verify MP4/GIF dimensions, durations, and sizes; preserve proof output paths and exact commands in the media README. Static story and alt text must convey the full flow without playback. Render is already authorized by the user.
