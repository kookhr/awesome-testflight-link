# Contributing

Thank you for your interest in contributing to this project!

## Adding a TestFlight Link

The easiest way to add a new link is through the **Add A TestFlight Link** GitHub Action workflow:

1. Go to **Actions** tab → **Add A TestFlight Link**
2. Click **Run workflow**
3. Fill in the required fields:
   - **testflight_link**: The full TestFlight join URL (e.g. `https://testflight.apple.com/join/AbcXYZ`)
   - **platforms**: Comma-separated platform list (e.g. `ios`, `ios,ipados`, `ios,ipados,macos,tvos`)
   - **app_name** (optional): App name if auto-detection fails

## Adding a Signup-Required App

For apps that require signup (no direct TestFlight link), edit `data/signup.md` directly and submit a PR.

## Deleting a Link

Use the **Delete A TestFlight Link** workflow in the Actions tab, providing the link ID or full URL.

## Data Format

Links are stored in `data/links.json` with this structure:

```json
{
  "_links": {
    "AbcXYZ": {
      "app_name": "App Name",
      "status": "Y",
      "tables": ["ios"],
      "last_modify": "2026-05-31"
    }
  }
}
```

### Fields

| Field | Description | Valid Values |
| --- | --- | --- |
| `app_name` | App display name (plain text, no HTML entities) | Any string |
| `status` | Current availability | `Y` (Available), `F` (Full), `N` (No), `D` (Deleted) |
| `tables` | Platforms this app supports | Array of: `ios`, `ipados`, `macos`, `tvos` |
| `last_modify` | Last status change date | `YYYY-MM-DD` format |

## Reporting Issues

If you find a broken or outdated link, please [open an issue](../../issues/new).
