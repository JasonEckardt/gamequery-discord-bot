"""
Scaffold only — not wired up yet.

Blockers to sort out before these can run:
  - main.py calls client.run(...) unconditionally at module scope (main.py:211),
    so `import main` will attempt a real Discord connection. Needs an
    `if __name__ == "__main__":` guard (or similar) before this file is usable.
  - ServerEmbed.build()/.query() are async but called without `await` inside
    ServerEmbed.__init__ and build() itself (main.py:41-43, main.py:73) — that
    looks like a bug, not a test problem. Tests below assume it gets fixed to
    something awaitable (e.g. build() called explicitly by the caller).
  - Needs `pytest-asyncio` (or anyio) installed; not added to requirements.txt.
"""

from unittest.mock import create_autospec

import discord
import pytest

from main import Protocol, ServerConfig, ServerEmbed, ServerStore, add_server


# ---- fixtures -------------------------------------------------------------

## To generate random embed_id: ` shuf -r -i 1-9 -z -n 19 `
@pytest.fixture
def server_store(tmp_path, monkeypatch):
    data = {
        "8885244214811133778": {
            "host": "latenightgame.servers",
            "name": "Abiotic Gamer",
            "port": "7777",
            "query_host": "10.0.3.10",
            "query_port": "27015",
            "protocol": "a2s",
            "embed_color": None,
            "embed_icon": None,
            "embed_id": 8885244214811133778,
            "embed_image": None,
        }
    }
    data_path = tmp_path / "pytest_data.json"
    data_path.write_text(json.dumps(data))
    monkeypatch.setattr(main, "OUT_SERVER_DATA", str(data_path))
    monkeypatch.setattr(main, "OUT_TMP", str(tmp_path / "server_data.tmp.json"))
    return main.ServerStore()

@pytest.fixture
def server_config_abioticfactor():
    # TODO: fill in a representative ServerConfig for a game server
    return ServerConfig(
        host="",
        name="",
        port=0,
        protocol=Protocol.NONE,
        query_host="",
        query_port=0,
        embed_color="",
        embed_icon=None,
        embed_id=None,
        embed_image=None,
    )


@pytest.fixture
def fake_interaction():
    # autospec'd against the real class so a typo'd attribute (e.g. .respones)
    # fails the test instead of silently returning a fresh Mock.
    interaction = create_autospec(discord.Interaction, instance=True)
    # `.response` is a property on the real class, so autospec can't see
    # through it to `InteractionResponse` on its own — spec it explicitly.
    interaction.response = create_autospec(discord.InteractionResponse, instance=True)
    return interaction


@pytest.fixture
def fake_channel():
    channel = create_autospec(discord.TextChannel, instance=True)
    # add_server does `message = await channel.send(...)` then reads `message.id`
    sent_message = create_autospec(discord.Message, instance=True)
    sent_message.id = 8885244214811133778 
    channel.send.return_value = sent_message
    return channel


# ---- ServerConfig / ServerStore --------------------------------------------

def test_server_store_update_writes_server_data(tmp_path, server_config):
    # TODO: point OUT_SERVER_DATA/OUT_TMP at tmp_path, or monkeypatch them
    pass


def test_server_store_delete_removes_entry():
    pass


# ---- ServerEmbed / a2s query -----------------------------------------------

@pytest.mark.asyncio
async def test_server_embed_build_sets_title_and_footer(server_config):
    # TODO: once build() is actually awaited, assert embed.title/footer/fields
    pass


@pytest.mark.asyncio
async def test_server_embed_query_a2s(monkeypatch, server_config):
    # TODO: monkeypatch a2s.info / a2s.rules so no real network call happens
    pass


# ---- add_server command -----------------------------------------------------

@pytest.mark.asyncio
async def test_add_server_sends_embed_and_responds(fake_interaction, fake_channel):
    # TODO: call add_server.callback(fake_interaction, host=..., name=..., ...)
    # and assert fake_channel.send was called + interaction.response.send_message
    pass
