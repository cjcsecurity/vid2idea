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

`scripts/prepare.mjs` builds both variants from `src/story.html` and copies the original SVG, local GSAP runtime, and two local WOFF2 fonts into independent self-contained `.build/demo/` and `.build/loop/` projects. Their render-time HTML makes no network requests. An optional `MEDIA_NODE_MODULES=/path/to/verified/node_modules` reuses an installation with the exact pinned package versions; an optional first script argument selects a temporary output directory. Build directories and dependency installs are ignored by Git.

After reviewing the preview, render the loop and film:

```bash
npx hyperframes render .build/loop --fps 25 --format gif --gif-loop 0 \
  --quality delivery --workers 1 --strict --output ../assets/vid2idea-preview.gif
npx hyperframes render .build/demo --fps 30 --quality delivery --workers 2 \
  --strict --output ../assets/vid2idea-demo.mp4
ffmpeg -y -ss 6.5 -i ../assets/vid2idea-demo.mp4 -frames:v 1 -q:v 3 \
  ../assets/vid2idea-poster.jpg
```

The settled 6.5-second brief frame is the separate poster. The MP4 starts with its actual opening composition: no unrelated frame is inserted before playback. The GIF runs at 25 fps for 12 seconds, with exact 40ms frame delays. Both variants use the same persistent layout and timed link transfer; the film also scrolls the same document to show first steps and a question that remains unresolved. The loop resets its document interior during the last second while the source, framing and typography stay anchored. An explicit full-frame background keeps GIF frames opaque.

Pinned dependencies are in `package.json` and `package-lock.json`: Hyperframes 0.8.106, GSAP 3.14.2, Manrope 5.3.0, JetBrains Mono 5.2.8. `npm audit` reported zero vulnerabilities on 2026-10-05.

## Verification

Run the browser gates for both variants and inspect the opening, link transfer, finished brief, scrolling document and final hold. The source uses one deterministic paused timeline and no scene cuts. There is no first-frame substitution or unrelated closing layout.

Verify the encoded GIF at the README's actual viewing width, including its 40ms frame delays, full opacity and continuous reset. Source PNG endpoints match exactly; GIF palette quantization changes 72 edge pixels, with no state or layout difference. Inspect the film's scroll at playback speed as well as in proof frames. The mobile SVG and reduced-motion poster remain readable static alternatives. Final measured checks are recorded in [verification.json](verification.json); temporary proofs, logs and build folders are excluded from the repository.

Both variants pass runtime, layout, motion and contrast gates with zero errors (84 text checks in the loop; 103 in the film). A single lint advisory notes that the same original static SVG appears in the message and its brief. The scrolling document has intentional clipping; direct measurements confirm the settled resource view and follow-up text fit inside the document viewport.

The MP4 has no audio stream. Both exports intentionally use silence; the choice and all licenses are recorded in [NOTICE.md](NOTICE.md). See [brag-plan.md](brag-plan.md), [composition-brief.md](composition-brief.md), and [shot-plan.json](shot-plan.json) for the creative contract. [share-copy.txt](share-copy.txt) is the short public caption.

Final delivered dimensions, duration, frame counts, and bytes are recorded in [verification.json](verification.json).
