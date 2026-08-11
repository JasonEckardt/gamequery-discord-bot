import shutil
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, create_autospec

import a2s
import cv2
import discord
import numpy as np
import pytest

import main

FIXTURE_SERVER_DATA = main.__file__.rsplit("/", 1)[0] + "/tests/fixtures/server_data.json"


# ---- ServerStore / path fixtures -------------------------------------------


@pytest.fixture
def store_paths(tmp_path, monkeypatch):
    data_path = tmp_path / "server_data.json"
    monkeypatch.setattr(main, "OUT_SERVER_DATA", str(data_path))
    monkeypatch.setattr(main, "OUT_TMP", str(tmp_path / "server_data.tmp.json"))
    return data_path


@pytest.fixture
def seeded_store_paths(store_paths):
    shutil.copy(FIXTURE_SERVER_DATA, store_paths)
    return store_paths


@pytest.fixture
def empty_store(store_paths):
    return main.ServerStore()


@pytest.fixture
def seeded_store(seeded_store_paths):
    return main.ServerStore()


@pytest.fixture
def server_store(seeded_store, monkeypatch):
    # `server_store` only exists as a module global once `if __name__ ==
    # "__main__":` has run, so raising=False is required here.
    monkeypatch.setattr(main, "server_store", seeded_store, raising=False)
    return seeded_store


@pytest.fixture
def empty_server_store(empty_store, monkeypatch):
    monkeypatch.setattr(main, "server_store", empty_store, raising=False)
    return empty_store


# ---- ServerConfig fixtures ---------------------------------------------------


@pytest.fixture
def server_config_none():
    return main.ServerConfig(
        host="Test",
        name="Test",
        port=1,
        protocol=main.Protocol.NONE,
        query_host=None,
        query_port=None,
        embed_color="#e74c3c",
        embed_id="1535777208965136449",
        embed_image=None,
        embed_thumbnail=None,
    )


@pytest.fixture
def server_config_a2s():
    return main.ServerConfig(
        host="lngs.lambdastack.org",
        name="Abiotic Gamer",
        port=7777,
        protocol=main.Protocol.A2S,
        query_host="10.0.3.108",
        query_port=27015,
        embed_color="#a6ffff",
        embed_id="1535769672082002011",
        embed_image="https://cdn2.steamgriddb.com/grid/bff359543d05cf44de980756af30c403.jpg",
        embed_thumbnail="https://cdn2.steamgriddb.com/logo/a0327e424a7f0233e8d20d444d3896c2.png",
    )


@pytest.fixture
def server_config_factory():
    def make_config(**overrides):
        defaults = dict(
            host="Test",
            name="Test",
            port=1234,
            protocol=main.Protocol.NONE,
            query_host=None,
            query_port=None,
            embed_color=None,
            embed_id=None,
            embed_image=None,
            embed_thumbnail=None,
        )
        defaults.update(overrides)
        return main.ServerConfig(**defaults)

    return make_config


# ---- a2s mocking --------------------------------------------------------------


@pytest.fixture
def mock_a2s(monkeypatch):
    info = a2s.SourceInfo(
        protocol=17,
        server_name="Test Server",
        map_name="TestMap",
        folder="testgame",
        game="Test Game",
        app_id=0,
        player_count=3,
        max_players=10,
        bot_count=0,
        server_type="d",
        platform="l",
        password_protected=False,
        vac_enabled=False,
        version="1.0",
        edf=0,
        ping=12.5,
    )
    rules = {"modCount": "3", "mods": "Mod A;Mod B", "StoryProgress_s": "42%"}

    ainfo = AsyncMock(return_value=info)
    arules = AsyncMock(return_value=rules)
    monkeypatch.setattr(main.a2s, "ainfo", ainfo)
    monkeypatch.setattr(main.a2s, "arules", arules)

    return SimpleNamespace(ainfo=ainfo, arules=arules, info=info, rules=rules)


# ---- image fetch mocking -------------------------------------------------------


@pytest.fixture
def solid_color_png_bytes():
    # Uniform BGR color: vivid/non-neutral per is_neutral's saturation<30 or
    # brightness>200 check, and deterministic under cv2.kmeans regardless of
    # KMEANS_RANDOM_CENTERS since every pixel is identical.
    img = np.full((20, 20, 3), (30, 30, 220), dtype=np.uint8)
    ok, encoded = cv2.imencode(".png", img)
    assert ok
    return encoded.tobytes()


@pytest.fixture
def mock_image_fetch(monkeypatch, solid_color_png_bytes):
    urlopen = Mock(return_value=Mock(read=Mock(return_value=solid_color_png_bytes)))
    monkeypatch.setattr(main.request, "urlopen", urlopen)
    return urlopen


# ---- discord object fixtures ----------------------------------------------------


@pytest.fixture
def fake_interaction():
    interaction = create_autospec(discord.Interaction, instance=True)
    # `.response`/`.followup` are properties on the real class, so autospec
    # can't traverse into them automatically — spec them explicitly.
    interaction.response = create_autospec(discord.InteractionResponse, instance=True)
    interaction.followup = create_autospec(discord.Webhook, instance=True)
    interaction.command = None
    return interaction


@pytest.fixture
def fake_channel():
    channel = create_autospec(discord.TextChannel, instance=True)
    sent_message = create_autospec(discord.Message, instance=True)
    sent_message.id = 9991234567890123456
    channel.send = AsyncMock(return_value=sent_message)
    channel.fetch_message = AsyncMock()
    return channel


@pytest.fixture
def fake_message_factory():
    def make_message(message_id, embeds=None):
        message = create_autospec(discord.Message, instance=True)
        message.id = message_id
        message.embeds = embeds or []
        message.edit = AsyncMock()
        message.delete = AsyncMock()
        return message

    return make_message


@pytest.fixture
def client_instance(fake_channel):
    instance = main.Client(intents=discord.Intents.default())
    instance.channel = fake_channel
    return instance


@pytest.fixture
def patched_client_channel(fake_channel, monkeypatch):
    monkeypatch.setattr(main.client, "channel", fake_channel, raising=False)
    return fake_channel


# ---- discord.ui component value helpers -----------------------------------------


def set_text_value(label, value):
    # TextInput.value has no public setter in discord.py 2.7.1's Label-based
    # API outside real interaction payloads; set the private backing field.
    label.component._value = value


def set_select_value(label, value):
    label.component._values = [value]
