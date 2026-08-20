# Scripts

Utility scripts for lafcbot development and maintenance.

## list_deal_ids.py

Lists all available deal IDs from lahomewin.com. This is useful for:
- Discovering deal IDs to add to the blacklist
- Finding deal IDs to configure in `deal_routes`
- Checking which deals are currently active

**Usage:**
```bash
uv run python scripts/list_deal_ids.py
```

**Output:**
- Groups deals by status (active, inactive, off-season)
- Shows deal details (restaurant, team, description, conditions)
- Provides a copy-paste ready list of all deal IDs for config.json

**Example blacklist configuration:**
```json
"dealsping": {
  "enabled": true,
  "blacklist": ["ono-hawaiian-bbq-lafc", "doordash-lafc"],
  ...
}
```
