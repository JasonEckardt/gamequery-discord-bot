# Steam App Icon for Embed Author

## Goal

Populate `ServerEmbed`'s author line (name, url, icon) from Steam store
metadata instead of leaving it unset. Author = game name, URL = Steam store
page, icon = Steam header image.

## Key fact: use `game_id`, not `app_id`

`a2s.SourceInfo.app_id` is a legacy uint16 field and truncates to `0` for
many modern App IDs — that's why both Abiotic Factor and Project Zomboid
show `app_id=0` in real queries. `game_id` (a2s/info.py:89) is the newer
64-bit field and holds the real App ID (427410, 108600). Check
`info.has_game_id` (a2s/info.py:109) before trusting it; fall back to
`app_id` only if it's unset.

## Approach

1. **Lookup helper.** Add an async function (`steam_app.py` or inline in
   `main.py`) that hits Steam's public appdetails endpoint:

   ```
   GET https://store.steampowered.com/api/appdetails?appids={game_id}
   ```

   Parse `data[str(game_id)]["success"]` and, if true, pull
   `data[...]["data"]["header_image"]` and `["name"]`. Store URL is just
   `f"https://store.steampowered.com/app/{game_id}/"` — no need to scrape it.
   Return `None` on `success: false` or a request error.

   No new dependency needed — `aiohttp` is already pulled in by
   `discord.py` (requirements.txt:2).

2. **Cache per `game_id`.** This metadata is static per game, so don't
   re-fetch it every query-loop tick. A plain in-memory dict
   (`{game_id: SteamAppInfo | None}`) on `ServerStore` is enough — it
   repopulates on process start and lives for the process lifetime, which
   matches how the query loop runs. Persisting it isn't necessary unless
   restarts become frequent enough to worry about Steam's rate limit.

3. **Wire into `ServerEmbed._query`** (main.py:69), after `a2s.ainfo`
   succeeds:

   ```python
   if info.has_game_id:
       steam_info = await steam_app.lookup(info.game_id)  # cached
       if steam_info:
           self.set_author(
               name=steam_info.name,
               url=steam_info.url,
               icon_url=steam_info.icon,
           )
   ```

   If `has_game_id` is false or the lookup misses, skip silently — existing
   `title` fallback (main.py:64-66) already covers the no-metadata case.

## Failure modes to handle

- Steam API request times out or errors → catch, log a `warn:` line
  consistent with the existing a2s warnings (main.py:83), continue without
  an author.
- `game_id` present but Steam returns `success: false` (delisted, private,
  or a non-Steam `folder`-only game) → cache `None` so we don't retry every
  tick, skip `set_author`.

## Open question

Steam's appdetails endpoint has an undocumented per-IP rate limit. The
in-memory cache should keep us well under it for a handful of servers, but
if the server list grows large or the process restarts often, consider
persisting the cache (e.g. alongside `server_data.json`) instead of
re-warming it from scratch each time.

## Files touched

- `main.py` — lookup helper + wiring into `ServerEmbed._query`
- no `requirements.txt` changes (aiohttp already present)
