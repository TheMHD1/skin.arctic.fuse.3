# Home view ordering

`home_view_order.py` reorders only `UserConfiguration.OrderedViews` for selected
Jellyfin users. It preserves every other configuration field, account policy,
library visibility and exclusions. Default execution is a dry run.

```sh
chmod 600 /private/jellyfin-api-key
python3 home_view_order.py --url https://jellyfin.example --api-key-file /private/jellyfin-api-key --all-users
python3 home_view_order.py --url https://jellyfin.example --api-key-file /private/jellyfin-api-key --user Ali --apply --journal /private/home-view-order.jsonl
```

Choose `--all-users` or one/more `--user` values explicitly; names are matched
case-insensitively. The order is Movies, Shows, Live TV, Venom Movies, Venom
Shows/Series, Shoko Anime, Collections, then unknown views. Existing unknown and
hidden OrderedViews IDs remain stable at the tail; the tool does not reveal or
enable hidden libraries.

Before POST it re-reads the complete user configuration and refuses any drift.
The 0600 private journal is fsync-appended before mutation and contains only user
ID plus `OrderedViews` before/after arrays. Restore is guarded: it first requires
current ordering to equal the journal's expected `after`, then restores only the
recorded `before` ordering while preserving newer unrelated preferences.

Run `python3 -m unittest test_home_view_order.py`.

The September 23 deployment applied this supported preference to 26 accounts
and verified every unchanged configuration field. The actual browser order was
Movies, Shows, Live TV, Venom Movies, Venom Series, Shoko Anime, Collections.
The existing library name `Venom Series` was deliberately not renamed: this
changes order only. Keep the private rollback journal outside this public fork.
