# Portfolio media

The [22-second demo](../assets/vid2idea-demo.mp4), [README loop](../assets/vid2idea-preview.gif), and [poster](../assets/vid2idea-poster.jpg) illustrate the local Discord-to-Notion workflow. **FrameForge is fictional, every URL uses example.com, and both interfaces are simulated.** These assets do not show a live end-to-end capture or a processing-speed benchmark. [Read the sample brief](../../examples/brief.md) for the full fictional output.

The film follows a saved link through the durable local queue, audio/on-screen text/frame evidence, separate opened-source research, and an illustrated resource-first Notion brief. The sample research answer is explicitly inconclusive. Optional project suggestions remain separate from observed resource facts.

## Static story and alt text

Suggested preview alt text: “Illustrated vid2idea workflow: a fictional FrameForge link saved in Discord passes through a durable local queue, audio/OCR/frames, and opened-source research into a resource-first Notion brief. Simulated interfaces.”

Without playback: save an article or public video link in Discord; the local collector keeps a durable job, extracts evidence, identifies featured resources, and researches follow-up questions with opened sources; the private Notion Library receives resource links and summaries first, then images, useful details, next steps, optional use cases, and visible coverage gaps. The computer must be awake to collect; the saved Notion pages remain readable afterward.

The README also uses a simplified portrait SVG on small screens and the poster for reduced-motion settings. Both convey the useful flow without animation.

## Rebuild locally

Media tooling is separate from the collector. Use Node.js 22 or newer, FFmpeg and FFprobe on PATH, and `unzip` for the managed Chrome download. The checked Linux build used Node.js 24. No collector, Discord bot, Notion credentials, audio provider, cloud rendering, or global skill installation is involved.

From this directory:

```bash
npm ci --ignore-scripts
npm run prepare:media
npx hyperframes browser ensure
npx hyperframes check .build/demo --json
npx hyperframes check .build/loop --json
npx hyperframes preview .build/demo --background
```

`scripts/prepare.mjs` copies the two source HTML files, original SVG, local GSAP runtime, and two local WOFF2 fonts into independent self-contained `.build/demo/` and `.build/loop/` projects. Their render-time HTML makes no network requests. An optional `MEDIA_NODE_MODULES=/path/to/verified/node_modules` reuses an installation with the exact pinned package versions; an optional first script argument selects a temporary output directory. Build directories and dependency installs are ignored by Git.

After reviewing the preview, render the loop and film:

```bash
npx hyperframes render .build/loop --fps 8 --format gif --gif-loop 0 \
  --quality delivery --workers 1 --strict --output ../assets/vid2idea-preview.gif
npx hyperframes render .build/demo --fps 30 --quality delivery --workers 2 \
  --strict --output .build/vid2idea-demo.raw.mp4
ffmpeg -y -ss 11.5 -i .build/vid2idea-demo.raw.mp4 -frames:v 1 -q:v 3 \
  ../assets/vid2idea-poster.jpg
ffmpeg -y -i .build/vid2idea-demo.raw.mp4 -i ../assets/vid2idea-poster.jpg \
  -filter_complex "[0:v][1:v]overlay=0:0:enable='eq(n,0)'[v]" -map '[v]' \
  -c:v libx264 -crf 18 -preset slow -pix_fmt yuv420p -movflags +faststart \
  ../assets/vid2idea-demo.mp4
```

The settled 11.5-second brief frame is the poster and the MP4's first frame. The rest of the film retains its original timing. The GIF uses 8 fps to keep the full 960-pixel typography within the size target; only restrained accents move, and all story text stays visible. Its explicit paper background child also keeps the GIF opaque during the alpha capture path.

Pinned dependencies are in `package.json` and `package-lock.json`: Hyperframes 0.8.106, GSAP 3.14.2, Manrope 5.3.0, JetBrains Mono 5.2.8. `npm audit` reported zero vulnerabilities on 2026-10-05.

## Verification

The final browser gates report zero errors for runtime, layout, motion assertions, and WCAG contrast. The demo passed 77 text checks; the loop passed 130. Loop lint has no warnings. Demo lint retains five advisory findings: four recommend extracting inline scenes into sub-compositions, and one flags repeated placements of the same original SVG. These are deliberate, simple inline scenes and still images; proof snapshots verify every scene mounts and displays correctly.

Inspected proof times: demo 0, 2, 6.5, 11.5, 15.5, 20.5, and 22 seconds; loop 0, 5.8, and 9 seconds. Focused keyframe inspection confirms the bounded link signal's motion. The decoded GIF was also inspected at 830 pixels wide, matching desktop GitHub rendering. The mobile SVG was inspected separately at a 324-pixel content width. Proof images, logs, and temporary raw encodes are excluded from the repository.

The MP4 has no audio stream. Both exports intentionally use silence; the choice and all licenses are recorded in [NOTICE.md](NOTICE.md). See [brag-plan.md](brag-plan.md), [composition-brief.md](composition-brief.md), and [shot-plan.json](shot-plan.json) for the creative contract. [share-copy.txt](share-copy.txt) is the short public caption.

Final delivered dimensions, duration, frame counts, and bytes are recorded in [verification.json](verification.json).
