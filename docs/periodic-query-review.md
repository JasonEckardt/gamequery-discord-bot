# Periodic A2S Query — Review Notes

Review of the `query_loop` / `ServerEmbed` refactor against the existing
`ServerConfig` and `ServerEmbed` class shapes. Line numbers refer to
`main.py` as of this review.

## Rough shape

- Refactor the query+field-building logic out of ServerEmbed.__init__ into an async method/function (constructors can't be async), since it needs to await the a2s calls.
- Add a @tasks.loop(seconds=N) task started in setup_hook that iterates server_store.servers, re-queries each via async a2s, rebuilds the embed, and edits the existing message (channel.fetch_message(embed_id) → .edit(embed=...)) rather than resending.
- Wrap each server's query in try/except so one offline/timing-out server doesn't break the loop or take down the others.

## Issues found

1. **`ServerEmbed.__init__` no longer takes `config`** (`main.py:41`, `:195`)
   `__init__(self, **kwargs)` only accepts keywords, but `add_server` still
   calls `ServerEmbed(new_server)` positionally — raises `TypeError`. Even
   fixed, `__init__` no longer calls `.build()`, so nothing populates the
   embed on the add-server path.

2. **`ServerEmbed.build()` called unbound in the loop** (`main.py:137`)
   ```python
   embed = await ServerEmbed.build(config)
   ```
   Calls `build` as an unbound function with `config` filling the `self`
   slot, so `self.set_thumbnail(...)` etc. run on a `ServerConfig` instance
   — `AttributeError`. Needs an instance first:
   `embed = ServerEmbed(); await embed.build(config)`.

3. **Missing `await` on the query call** (`main.py:72`)
   ```python
   self.query(config.query_host, config.query_port, config.protocol)
   ```
   `query` is `async def`; without `await` this just creates and drops a
   coroutine — a2s is never actually queried.

4. **`ServerConfig(config)` from the stored dict** (`main.py:136`)
   `server_store.servers.items()` yields `(embed_id, dict)` pairs (see
   `ServerStore.update`, `main.py:103-115`). `ServerConfig` is a 10-field
   positional dataclass, so `ServerConfig(config)` jams the whole dict into
   `host` and fails on missing args. Needs `ServerConfig(**config)` plus
   coercion: `protocol` is stored as a string (`Protocol(config["protocol"])`)
   and `port`/`query_port` are stored as strings (`int(...)`).

5. **Exception handler references the broken variable** (`main.py:142`)
   Since `config = ServerConfig(config)` fails before reassignment, `config`
   in the `except` block is still the raw dict, so `config.name` raises
   `AttributeError` inside the handler itself, masking the real error.

6. **`channel.send(embed)` missing the `embed=` keyword** (`main.py:138`)
   `TextChannel.send`'s first positional parameter is `content: str`, not
   `embed`. Needs `self.channel.send(embed=embed)`.

7. **Sends a new message every tick instead of editing the existing one**
   (`main.py:138-139`)
   Even with (6) fixed, the loop `send()`s a brand-new message then
   `.edit()`s *that* new message — every interval posts a fresh message
   instead of updating the one referenced by `embed_id`. Should be:
   ```python
   message = await self.channel.fetch_message(int(embed_id))
   await message.edit(embed=embed)
   ```

8. **`PING_INTERVAL` env var passed as a string** (`main.py:132`)
   `os.getenv("PING_INTERVAL") or 60` returns a `str` when set, and
   `tasks.loop(seconds=...)` builds a `timedelta` from it —
   `timedelta(seconds="30")` raises `TypeError`. Needs
   `int(os.getenv("PING_INTERVAL", 60))`.

## Correct shape

The intended flow per loop tick, per stored server:

1. Rebuild a `ServerConfig` from the stored dict (with type coercion).
2. Construct a fresh `ServerEmbed()` instance.
3. `await embed.build(config)` (which internally `await`s `query(...)`).
4. Fetch the existing message by `embed_id` and `.edit(embed=embed)` it —
   never `send()` a new one for updates.

## Still open (noted, not blocking)

- `query()` calls the **synchronous** `a2s.info`/`a2s.rules` from inside an
  `async def`. This blocks the event loop/gateway heartbeat while the
  query is in flight. Consider `a2s.ainfo`/`a2s.arules` if unreachable
  servers or slow queries become an issue.
