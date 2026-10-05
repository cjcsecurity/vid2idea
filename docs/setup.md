# Discord and Notion setup

Run the installation commands in the root README first. Create configuration with `vid2idea init` from `collector/`. Edit `collector/.env` locally; do not change its private permissions. Run commands there, or supply `--env-file /absolute/path/to/collector/.env`. The collector reads that exact file, does not search parent folders, and does not expand `${VARIABLE}` placeholders. Exported environment variables take precedence. Do not publish your Notion workspace or create a new cloud application.

## Discord

1. Create an application and bot in the [Discord Developer Portal](https://discord.com/developers/applications).
2. Enable **Message Content Intent** on the bot. Invite it to your server with **View Channel** and **Read Message History**, limited to the intended channel. Send-message permission is unnecessary; this collector does not post messages.
3. Save the bot token as `DISCORD_TOKEN` locally. Enable Discord Developer Mode and copy the channel ID into `DISCORD_CHANNEL_ID`.
4. Optionally set `DISCORD_AUTHOR_ID` to your user ID. Leave it empty to collect all non-bot posts in that channel. Additional text beside a link can supply brief context.

## Notion connection and project

As a workspace owner, create an [internal Notion connection](https://developers.notion.com/guides/get-started/internal-connections) with read, insert and update content capabilities. In the connection’s **Content access → Edit access**, grant it access to **Library**, **Projects**, and the project page you use below. Alternatively use each Notion page’s **••• → Connections → Add connection**. Access to a parent includes its children. Save its token as `NOTION_API_TOKEN` locally. Connection access is sufficient; the databases can remain private.

Create or reuse a **Projects** database/data source. Its title property can be `Name`; the publisher does not require a broader project-management schema. Add a project page such as **Saved ideas**. Save that page's ID as `NOTION_VID2IDEA_PROJECT_PAGE_ID`. Despite the variable name, it can be any page in your Projects data source. New entries initially relate to this page; you can change their project relations afterward.

## Exact Library schema

Create a **Library** database with these property names, types and options. Use **Select**, not the separate Notion **Status** type, for the rows below marked Select. Extra properties and extra select options are allowed; all listed names/options are required.

| Property | Notion UI type | Required options / destination |
| --- | --- | --- |
| Name | Title | Rename the database title property |
| Origin | Select | Manual, Codex, vid2idea |
| Source URL | URL | |
| Summary | Text | |
| Topics | Multi-select | Options may be created during publication |
| Last published | Date | |
| Processing status | Select | Queued, Processing, Ready, Partial, Blocked, Failed |
| Error code | Text | |
| External ID | Text | |
| Content hash | Text | |
| Kind | Select | Article |
| Saved at | Date | |
| Projects | Relation | The Projects data source; allow multiple pages |
| Review status | Select | Unread, Reviewed, Archived |
| Stage | Select | Saved, Trying, Done |
| Favorite | Checkbox | |
| Personal notes | Text | |
| Refresh article | Checkbox | |

The API calls UI Text properties `rich_text`. Do not edit generated External ID or Content hash values. The publisher verifies this schema before publishing.

## Find the right IDs

Notion database IDs, data source IDs and page IDs are different. The collector requires `NOTION_LIBRARY_DATA_SOURCE_ID` and `NOTION_PROJECTS_DATA_SOURCE_ID`, plus the project page ID. `NOTION_LIBRARY_DATABASE_ID` is optional metadata.

For page/database IDs, copy the item's link: the 32 hexadecimal characters near the end of its path are the ID; query parameters such as the view ID are not the page ID. For data source IDs, use Notion's data source controls if they expose the ID, or use the official [Search endpoint](https://developers.notion.com/reference/post-search) with the connection token. Search returns only content shared with the connection. The example below runs locally and prints data source titles and IDs, not the token:

```bash
# From collector/, after saving NOTION_API_TOKEN in the private .env:
uv run --locked --extra media vid2idea notion-sources
```

This read-only command prints source names and IDs, never your token. If it returns an empty list, grant access to the actual database pages and try again. It does not create or change your databases.

Match the actual Library and Projects sources, especially if there are duplicate names or multiple sources in a database. The Library Projects relation must point to the same source you configure. See [Notion data source retrieval](https://developers.notion.com/reference/retrieve-a-data-source).

## Validate and verify a real source

From `collector/`, run:

```bash
uv run --locked --extra media vid2idea doctor --check-notion
uv run --locked --extra media vid2idea import-history
uv run --locked --extra media vid2idea run
```

Doctor must report no missing configuration and a verified Notion connection. It checks media prerequisites, Codex subscription login, and Notion access/schema/project membership. It does not prove every platform can download or that Codex has remaining usage. Post a short public source, then inspect the full Notion page before enabling autostart.

Useful Library views: recent entries sorted by Saved at; Favorites; unread briefs; and Partial/Blocked/Failed items for review. Check **Refresh article** to request regeneration/research. See [operations](operations.md) before changing or restoring local state.
