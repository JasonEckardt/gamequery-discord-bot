# pytest, for an RSpec person

Notes from working through the first real test for `ServerStore`. Written as
a reference to come back to, not a tutorial to read top-to-bottom.

## Concept mapping

| RSpec | pytest |
|---|---|
| `describe`/`context` block | Not required. A `test_*.py` file with plain functions is enough. |
| `it "does X" do ... end` | `def test_does_x(): ...` |
| `expect(x).to eq(y)` | `assert x == y` — plain Python `assert`. pytest rewrites it at import time to show a rich diff on failure, so you don't need a matcher DSL. |
| `expect { }.to raise_error(Foo)` | `with pytest.raises(Foo): ...` |
| `let(:foo) { ... }` / `before` | `@pytest.fixture` — see below, works differently than `let`. |
| `allow(obj).to receive(:method)` | `monkeypatch.setattr(obj, "method", ...)` |

The big mental shift from RSpec: **fixtures are injected by parameter name,
not implicit block magic.** If a test's signature is
`def test_foo(server_store):`, pytest looks for something named
`server_store` — either a fixture you defined with `@pytest.fixture`, or one
of pytest's built-ins — runs it, and passes the return value in as the
argument. There's no scoping via `describe` blocks; a fixture used by one
test file is just a plain function decorated with `@pytest.fixture`.

## Built-in fixtures used below

- **`tmp_path`** — no import, no definition needed. A fresh `pathlib.Path`
  pointing at a unique temp directory, created before the test and cleaned
  up after. Closest RSpec analogue is manually doing `Dir.mktmpdir`, except
  pytest wires it up for you automatically.
- **`monkeypatch`** — also built-in. Patches attributes / env vars / dict
  entries and **automatically reverts them after the test**, similar to how
  RSpec resets `allow(...).to receive(...)` doubles between examples.

## The gotcha: patching module-level globals

`main.py` has two module-level constants:

```python
OUT_TMP = "./server_data.tmp.json"
OUT_SERVER_DATA = "./server_data.json"
```

`ServerStore.__init__`/`_apply` read these by name at call time
(`open(OUT_SERVER_DATA, "r")`). Python looks that name up in `main`'s
module namespace *every time the function runs* — so reassigning
`main.OUT_SERVER_DATA` before constructing a `ServerStore` redirects its
file I/O, no real file in the repo gets touched.

This only works if the test file does `import main` and patches
`main.OUT_SERVER_DATA`. Doing `from main import OUT_SERVER_DATA` and
patching the *test file's* local copy would not affect what `main.py`'s own
functions see — they'd still read the original module-level value.

## Worked example: round-trip test

Goal: prove `ServerStore.update()` persists data that survives being
reloaded from disk — not just that it mutates an in-memory dict.

```python
def test_server_store_update_writes_server_data(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "OUT_SERVER_DATA", str(tmp_path / "server_data.json"))
    monkeypatch.setattr(main, "OUT_TMP", str(tmp_path / "server_data.tmp.json"))

    store = main.ServerStore()
    config = main.ServerConfig(
        host="latenightgame.servers",
        name="Abiotic Gamer",
        port=7777,
        protocol=main.Protocol.A2S,
        query_host="10.0.3.10",
        query_port=27015,
        embed_color=None,
        embed_id="8885244214811133778",
        embed_image=None,
        embed_thumbnail=None,
    )

    store.update(config)

    reloaded = main.ServerStore()
    assert reloaded.servers["8885244214811133778"]["host"] == "latenightgame.servers"
    assert reloaded.servers["8885244214811133778"]["port"] == 7777
```

Walking through it:

1. **Redirect the paths first.** Both `OUT_SERVER_DATA` and `OUT_TMP` get
   pointed inside `tmp_path` before anything touches `ServerStore`, since
   `_apply()` writes to `OUT_TMP` then does `os.replace()` onto
   `OUT_SERVER_DATA` (`main.py:210-212`) — both need redirecting or the
   `os.replace` would land in two different places.
2. **`store.update(config)`** calls the real `update()` (`main.py:218-232`),
   which requires a non-`None` `embed_id` (it early-returns and logs an
   error otherwise) — that's why the fixture config sets one explicitly.
3. **`reloaded = main.ServerStore()`** is a second, independent instance.
   This is the actual point of a round-trip test: checking `store.servers`
   directly only proves the in-memory dict was set, which is trivial.
   Constructing a *new* instance forces it through `__init__`'s
   `json.load`, proving `_apply()` wrote valid, readable JSON.
4. **The asserts use a string key** (`"8885244214811133778"`) because
   `update()` does `self.servers[str(config.embed_id)] = {...}`
   (`main.py:225`) — and JSON object keys always deserialize as strings
   regardless of what type they started as, so this is also what a fresh
   `json.load` would hand back either way.

Verified this passes against the real `main.py` before writing it down here.

## Practice exercise (not yet attempted)

Write `test_server_store_delete_removes_entry`, following the same shape:
redirect the paths, seed an entry via `update()`, call `delete()`, then
reload with a fresh `ServerStore()` and assert the key is gone
(`main.py:215-217` — `delete()` is a two-liner, so the test should be
shorter than the one above).

Hint: asserting the key is gone from `reloaded.servers` is stronger than
asserting it's gone from `store.servers` — same reasoning as step 3 above.
