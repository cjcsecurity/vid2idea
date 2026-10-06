# Choose an AI provider

The coding agent you use to install or edit vid2idea is independent of the provider that processes saved links. You can maintain the repository with Codex, Claude Code, Gemini CLI, Cursor, or another terminal-capable assistant. The collector's runtime choices are below.

| `AI_PROVIDER` | Authentication | Briefs and sampled images | Follow-up research | Verification |
| --- | --- | --- | --- | --- |
| `codex` (default) | ChatGPT login | Yes | Live search and opened citations | Existing live workflow verified; CLI 0.160.0 |
| `claude` | Claude subscription login | Yes | WebSearch and WebFetch | Experimental; CLI 2.1.290 contract/regression checks; authenticated end-to-end run still needed |
| `gemini` | Google login in a collector-specific profile | Yes | Google search and direct web fetch | Experimental; CLI 0.62.0 contract/regression checks; authenticated end-to-end run still needed |
| `openai` | Explicit API endpoint/key | Images require `AI_VISION_MODEL` | Disabled | Existing compatible-endpoint adapter; endpoint capabilities vary |

Account eligibility, model availability and usage limits belong to the provider. A coding subscription does not provide an API key for other providers. CLI modes never fall back to a paid API. Model settings left blank use the selected CLI's default; set `CODEX_MODEL`, `CLAUDE_MODEL`, or `GEMINI_MODEL` to choose an available model explicitly.

## Install one CLI

Use Node.js 24. Install only your chosen provider, then set `AI_PROVIDER` in `collector/.env`:

```bash
# Choose ONE:
npm install -g @openai/codex@0.160.0
npm install -g @anthropic-ai/claude-code@2.1.290
npm install -g @google/gemini-cli@0.62.0
```

The new adapters require these exact Claude/Gemini versions because tool permissions, configuration and event formats are part of the safety contract. An unreviewed version fails with `*_unsupported_version`. If another version is needed for your coding work, install the pinned package into a separate npm prefix and put its executable's absolute path in `CLAUDE_COMMAND` or `GEMINI_COMMAND`. You do not need to change your usual coding-agent installation.

## Sign in and check

From `collector/`, after `vid2idea init` and setting your provider:

```bash
uv run --locked --extra media vid2idea auth
uv run --locked --extra media vid2idea doctor --check-ai --check-notion
```

- **Codex:** choose ChatGPT authentication. An existing normal Codex login is reused.
- **Claude:** sign in with your Claude subscription. An existing normal Claude Code login is reused. API-key and Console authentication are rejected by this adapter.
- **Gemini:** choose **Sign in with Google**, complete the browser/code flow, then enter `/quit`. Login is saved by Gemini under `DATA_DIR/gemini-home`; the collector does not copy or read your ordinary Gemini credentials. Keep this directory private and use it only for the collector. Re-run `vid2idea auth` with the same `.env` to renew it.

`--check-ai` consumes provider quota for one small fictional text brief. It publishes nothing and sends no personal project context. It verifies generation, not video extraction or live research. A normal doctor run checks prerequisites without model inference; Gemini reports `login_unverified` until a model check succeeds. This is not a claim that credentials or remaining quota are valid.

Post one short public link, confirm resource names, images and research in Notion, then enable autostart. Run the service as the same OS user and with the same configuration/PATH used during setup. Account access is still needed to finish authenticated validation of the experimental adapters; fixture tests alone do not prove a live workflow.

## API-compatible endpoints

Set `AI_PROVIDER=openai`, `AI_BASE_URL` and `AI_MODEL`; add `AI_API_KEY` when required. Set `AI_VISION_MODEL` only if that endpoint accepts image messages. A local compatible model may need no key. API usage can incur charges. Automatic question research is disabled in this mode, and the saved brief reports that limitation.

## Isolation and research limits

Generation receives evidence and explicit image attachments without model tool access. Research receives a separate public-only payload and permits web tools. Personal project descriptions and Discord notes are excluded from research. CLI hooks, skills and connected tools are disabled for these calls; Gemini uses a separate login profile. Administrator-managed policies may still apply.

Gemini input escapes untrusted `@file` syntax before adding its own sampled frames. Claude and Gemini research use the existing public-address safety proxy. Structured output is validated before publication. Search snippets and model-written citations alone cannot verify an answer: citations must match successful page-fetch events. Redirects or unexpected event formats may leave an answer inconclusive. Provider CLI state is local, and these controls are not an operating-system sandbox.

Contracts checked against [Codex non-interactive mode](https://developers.openai.com/codex/noninteractive/), [Claude Code CLI reference](https://code.claude.com/docs/en/cli-reference), [Gemini headless mode](https://geminicli.com/docs/cli/headless/), [Gemini configuration](https://geminicli.com/docs/reference/configuration/), and the installed pinned CLIs. See [operations](operations.md) for recovery.
