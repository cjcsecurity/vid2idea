# Brag plan: vid2idea

This is a silent, 22-second, 16:9 portfolio demo. It depicts a **simulated flow**, not a live capture or a processing-speed benchmark. FrameForge and all example.com addresses are fictional. No private operational data or borrowed source imagery is used.

## Nine-question rubric

1. **What is it?** A local collector that turns links saved in Discord into illustrated, researched briefs in a private Notion Library.
2. **Strongest claim:** “Save a link in Discord. Revisit an illustrated, researched brief in Notion.” The impressive part is identifying a resource that is shown on screen, then putting that resource first in the brief.
3. **Visual hook:** An ordinary Discord link becomes a warm, editorial Notion page. A retained link chip gives the transition a clear subject.
4. **Actual output to show:** Native block order from `collector/src/vid2idea/notion_content.py`: resource heading, linked address, resource summary, Summary, source image with caption, Useful details, First steps, Ways to use this, Research, Still to figure out, Coverage notes. The simulated page condenses this output while keeping resource names, links and summary first; selected sections remain visible at useful scale.
5. **Shortest satisfying video:** 22 seconds gives the entry, evidence pass, and resource-first result enough reading time.
6. **Tone:** polished. Creative direction: a thoughtful editorial film about recovering useful ideas. Crisp typography, physical paper, calm purposeful motion, restrained coral and lime.
7. **Audio:** intentional silence. README playback is muted by nature; silence carries across the longer demo. No narration, music, or SFX. Bundled music is excluded because public redistribution rights have not been established.
8. **Share caption:** vid2idea turns links saved in Discord into illustrated briefs in your Notion Library, with resource links, opened-source research, and useful next steps. This demo uses a clearly fictional example.
9. **User flow:** save a Discord link → retain it in the local durable queue and analyze audio/on-screen text/frames → revisit a resource-first Notion brief with research and optional use cases.

## Angle and identity

**Hook:** “Keep the idea. Get the context.” The saved link and its destination share one frame from the start.

**Centerpiece:** A simulated Discord message with a fictional FrameForge link transforms into an illustrated Notion brief. The middle explains how local evidence and separate opened-source research support that destination.

**Finish:** return to the resource heading in the same document. The original saved link stays visible; no independent closing scene.

The repository has no product web UI. This revision preserves the established media palette: ink `#17252b`, paper `#f4f0e7`, coral `#b74331`, lime `#d4e897`, muted ink `#56655f`, pale line `#d8d7cb`. Manrope is the main face; JetBrains Mono labels local processing and addresses. Type is sized for an 800–960px README rendition. No neon, glow, synthetic statistics, or resurrected dashboard.

## Grounding

| On-screen idea | Repository evidence |
| --- | --- |
| Discord → local durable queue → audio, OCR, frames → Notion | `README.md`, `docs/architecture.md` |
| Resource names and links before applications | `README.md`, `render_article()` in `collector/src/vid2idea/notion_content.py` |
| Research keeps successfully opened sources and checked dates | `docs/architecture.md`, `notion_content.py` |
| Optional project-specific use cases | `README.md`, `examples/brief.md` |
| FrameForge screenshot cards; folder/title/PNG details | Fictional copy in `examples/brief.md` |
| Sample batch-mode answer remains inconclusive | `examples/brief.md`; no invented citation |

## Storyboard — 22 seconds

One persistent composition replaces independent scene entrances. The source, document chrome, headline and footer keep their positions throughout. Motion communicates a saved link becoming a useful brief, with space to read the result.

1. **Save and hand off — 0–4s.** The fictional Discord message is already visible. Queue acknowledgment and two evidence/research indicators complete in order. A link token travels right into the existing document frame with a smooth ease; it does not reverse or wobble.
2. **Reveal the resource — 4–9s.** The empty-state explanation gives way to the resource name, address and summary. Its original illustration and useful details follow. The finished resource view holds for reading.
3. **Read the next steps — 9–18s.** The same document scrolls upward. A small first step and batch-export question remain visible for a long reading hold. “Still to verify” makes the fictional example's evidence limit explicit.
4. **Keep the context — 18–22s.** The document returns to its heading and settles. The original message remains beside the resource-first brief.

**Audio summary:** silence throughout; motion timing serves reading, not beat synchronization. The MP4 starts at the real opening frame. A separate 6.5-second result frame supplies the static poster.

## Short README loop

12 seconds, 960×540, 25fps GIF. It uses the same composition and first six seconds of motion as the film, then holds the complete resource view. During the last second only the document interior and status indicators reset; the source and frame remain anchored. Source endpoint frames match; any encoded palette differences are measured separately from layout continuity. The mobile portrait SVG and reduced-motion poster remain static alternatives.
