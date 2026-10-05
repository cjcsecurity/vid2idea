# Discord and Notion setup

Run the installation commands in the root README first. Keep configuration in `collector/.env`; all commands that load it should run from `collector/`. Do not publish your Notion workspace or create a new cloud application.

## Discord

1. Create an application and bot in the [Discord Developer Portal](https://discord.com/developers/applications).
2. Enable **Message Content Intent** on the bot. Invite it to your server with **View Channel** and **Read Message History**, limited to the intended channel. Send-message permission is unnecessary; this collector does not post messages.
3. Save the bot token as `DISCORD_TOKEN` locally. Enable Discord Developer Mode and copy the channel ID into `DISCORD_CHANNEL_ID`.
4. Optionally set `DISCORD_AUTHOR_ID` to your user ID. Leave it empty to collect all non-bot posts in that channel. Additional text beside a link can supply brief context.

## Notion connection and project

Create an [internal Notion connection](https://developers.notion.com/guides/get-started/internal-connections) with read, insert and update content capabilities. Grant it access to **Library**, **Projects**, and the project page you use below. Save its token as `NOTION_API_TOKEN` locally. Connection access is sufficient; the databases can remain private.

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
# Bash, from collector/. Do not enable shell tracing.
read -rsp 'Notion connection token: ' notion_setup_token
export notion_setup_token
uv run --locked python - <<'PY'
import os
import httpx
token = os.environ.pop('notion_setup_token')
headers = {'Authorization': 'Bearer ' + token, 'Notion-Version': '2026-03-11'}
with httpx.Client(headers=headers, timeout=30) as client:
    cursor = None
    while True:
        body = {'filter': {'property': 'object', 'value': 'data_source'}, 'page_size': 100}
        if cursor:
            body['start_cursor'] = cursor
        response = client.post('https://api.notion.com/v1/search', json=body)
        if not response.is_success:
            raise SystemExit(f'Notion search failed: HTTP {response.status_code}')
        data = response.json()
        for item in data['results']:
            title = ''.join(part.get('plain_text', '') for part in item.get('title', []))
            print(title, item['id'])
        if not data.get('has_more'):
            break
        cursor = data['next_cursor']
PY
unset notion_setup_token
```

Match the actual Library and Projects sources, especially if there are duplicate names or multiple sources in a database. The Library Projects relation must point to the same source you configure. See [Notion data source retrieval](https://developers.notion.com/reference/retrieve-a-data-source).

## Validate and verify a real source

From `collector/`, run:

```bash
uv run --locked --extra media vid2idea doctor --check-notion
uv run --locked --extra media vid2idea import-history
uv run --locked --extra media vid2idea run
```

Doctor must report no missing configuration and a verified Notion connection. It checks media prerequisites and Notion access/schema; it does not prove every platform can download or that Codex has remaining usage. Confirm `codex login status` separately. Post a short public source, then inspect the full Notion page before enabling autostart.

Useful Library views: recent entries sorted by Saved at; Favorites; unread briefs; and Partial/Blocked/Failed items for review. Check **Refresh article** to request regeneration/research. See [operations](operations.md) before changing or restoring local state.
