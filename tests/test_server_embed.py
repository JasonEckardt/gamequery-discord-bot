import re
from unittest.mock import Mock
from urllib import error

import a2s
import pytest

import main


def clamp(value):
    return min(255, int(value))


# ---- __init__ / base fields -------------------------------------------------


def test_init_sets_status_pending_and_base_fields(server_config_none):
    embed = main.ServerEmbed(server_config_none)

    assert embed.status == main.ServerStatus.PENDING
    assert embed.tries == 0
    assert embed.update is False

    fields = {f.name: f.value for f in embed.fields}
    assert fields["Host"] == server_config_none.host
    assert fields["Port"] == str(server_config_none.port)
    assert fields["Name"] == server_config_none.name


# ---- color logic -------------------------------------------------------------


def test_init_with_explicit_embed_color_uses_it_without_network(
    server_config_factory, monkeypatch
):
    urlopen = Mock(side_effect=AssertionError("urlopen should not be called"))
    monkeypatch.setattr(main.request, "urlopen", urlopen)

    config = server_config_factory(embed_color="#ff0000")
    embed = main.ServerEmbed(config)

    assert str(embed.color) == "#ff0000"
    urlopen.assert_not_called()


def test_init_with_no_color_and_no_image_picks_random_preset(
    server_config_factory, monkeypatch
):
    forced_color = main.ServerEmbed._RANDOM_EMBED_COLORS[3]
    choice = Mock(return_value=forced_color)
    monkeypatch.setattr(main.random, "choice", choice)

    config = server_config_factory(embed_color=None, embed_image=None, embed_thumbnail=None)
    embed = main.ServerEmbed(config)

    assert embed.color == forced_color
    choice.assert_called_once_with(main.ServerEmbed._RANDOM_EMBED_COLORS)


def test_init_derives_color_from_image_success(
    server_config_factory, mock_image_fetch
):
    config = server_config_factory(
        embed_color=None,
        embed_image="https://example.com/banner.png",
        embed_thumbnail=None,
    )
    embed = main.ServerEmbed(config)

    hex_str = str(embed.color)
    assert re.match(r"^#[0-9a-f]{6}$", hex_str)

    # Fixture image is a uniform BGR (30, 30, 220) pixel; kmeans on a
    # single-color image deterministically converges to that same color.
    b, g, r = 30, 30, 220
    expected = main.discord.Color.from_rgb(
        clamp(r * 1.5), clamp(g * 1.5), clamp(b * 1.5)
    )
    assert embed.color == expected


def test_init_derives_color_from_thumbnail_when_no_image(
    server_config_factory, mock_image_fetch
):
    config = server_config_factory(
        embed_color=None,
        embed_image=None,
        embed_thumbnail="https://example.com/thumb.png",
    )
    main.ServerEmbed(config)

    requested_url = mock_image_fetch.call_args[0][0].full_url
    assert requested_url == "https://example.com/thumb.png"


def test_init_image_network_error_falls_back_to_random_color(
    server_config_factory, monkeypatch
):
    urlopen = Mock(side_effect=error.URLError("boom"))
    monkeypatch.setattr(main.request, "urlopen", urlopen)

    config = server_config_factory(
        embed_color=None, embed_image="https://example.com/banner.png"
    )
    embed = main.ServerEmbed(config)

    assert embed.color in main.ServerEmbed._RANDOM_EMBED_COLORS


def test_init_image_decode_failure_falls_back_to_random_color(
    server_config_factory, monkeypatch
):
    urlopen = Mock(return_value=Mock(read=Mock(return_value=b"not an image")))
    monkeypatch.setattr(main.request, "urlopen", urlopen)

    config = server_config_factory(
        embed_color=None, embed_image="https://example.com/banner.png"
    )
    embed = main.ServerEmbed(config)

    assert embed.color in main.ServerEmbed._RANDOM_EMBED_COLORS


# ---- ServerEmbed.build --------------------------------------------------------


@pytest.mark.asyncio
async def test_build_with_explicit_embed_color_skips_store_pin_back(
    server_config_factory, monkeypatch
):
    fake_store = Mock()
    monkeypatch.setattr(main, "server_store", fake_store, raising=False)

    config = server_config_factory(embed_color="#ff0000", protocol=main.Protocol.NONE)
    await main.ServerEmbed.build(config)

    fake_store.update.assert_not_called()


@pytest.mark.asyncio
async def test_build_without_embed_color_pins_resolved_color_and_updates_store(
    server_store, server_config_factory
):
    config = server_config_factory(
        embed_color=None, embed_id="1535777208965136449", protocol=main.Protocol.NONE
    )

    await main.ServerEmbed.build(config)

    assert config.embed_color is not None
    assert re.match(r"^#[0-9a-f]{6}$", config.embed_color)
    assert (
        server_store.servers["1535777208965136449"]["embed_color"]
        == config.embed_color
    )


@pytest.mark.asyncio
async def test_build_without_embed_color_and_without_embed_id_skips_store_update(
    server_store, server_config_factory, monkeypatch
):
    spy = Mock(wraps=server_store.update)
    monkeypatch.setattr(server_store, "update", spy)

    config = server_config_factory(
        embed_color=None, embed_id=None, protocol=main.Protocol.NONE
    )
    await main.ServerEmbed.build(config)

    spy.assert_not_called()


@pytest.mark.asyncio
async def test_build_sets_update_true_when_status_differs_from_previous(
    server_config_factory,
):
    config = server_config_factory(embed_color="#ff0000", protocol=main.Protocol.NONE)
    embed = await main.ServerEmbed.build(
        config, previous_status=main.ServerStatus.OFFLINE
    )

    assert embed.status == main.ServerStatus.UNQUERIED
    assert embed.update is True


@pytest.mark.asyncio
async def test_build_sets_update_false_when_status_matches_previous(
    server_config_factory,
):
    config = server_config_factory(embed_color="#ff0000", protocol=main.Protocol.NONE)
    embed = await main.ServerEmbed.build(
        config, previous_status=main.ServerStatus.UNQUERIED
    )

    assert embed.update is False


@pytest.mark.asyncio
async def test_build_sets_title_to_config_name_when_update_true_and_title_unset(
    server_config_factory,
):
    config = server_config_factory(
        embed_color="#ff0000", name="My Server", protocol=main.Protocol.NONE
    )
    embed = await main.ServerEmbed.build(config)

    assert embed.title == "My Server"


@pytest.mark.asyncio
async def test_build_footer_omits_icon_for_unqueried_status(server_config_factory):
    config = server_config_factory(
        embed_color="#ff0000", host="h", port=1, protocol=main.Protocol.NONE
    )
    embed = await main.ServerEmbed.build(config)

    assert embed.footer.icon_url is None
    assert embed.footer.text == "h:1"


@pytest.mark.asyncio
async def test_build_footer_includes_status_icon_for_queried_status(
    server_config_a2s, mock_a2s
):
    server_config_a2s.embed_color = "#ff0000"
    embed = await main.ServerEmbed.build(server_config_a2s)

    assert embed.footer.icon_url is not None
    assert "Online.png" in embed.footer.icon_url
    assert embed.footer.text.startswith("Online  •  ")


# ---- _query -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_query_protocol_none_sets_unqueried(server_config_factory):
    config = server_config_factory(embed_color="#ff0000", protocol=main.Protocol.NONE)
    embed = main.ServerEmbed(config)

    await embed._query(config.query_host, config.query_port, config.protocol, config.name)

    assert embed.status == main.ServerStatus.UNQUERIED


@pytest.mark.asyncio
async def test_query_a2s_success_sets_online_and_core_fields(
    server_config_a2s, mock_a2s
):
    embed = main.ServerEmbed(server_config_a2s)

    await embed._query(
        server_config_a2s.query_host,
        server_config_a2s.query_port,
        server_config_a2s.protocol,
        server_config_a2s.name,
    )

    assert embed.status == main.ServerStatus.ONLINE
    assert embed.tries == 0
    assert embed.title == mock_a2s.info.game

    fields = {f.name: f.value for f in embed.fields}
    assert fields["Players"] == "3/10"
    assert fields["Game Version"] == "1.0"


@pytest.mark.asyncio
async def test_query_a2s_success_abiotic_factor_adds_story_progress_field(
    server_config_a2s, mock_a2s
):
    mock_a2s.info.game = "Abiotic Factor"
    embed = main.ServerEmbed(server_config_a2s)

    await embed._query(
        server_config_a2s.query_host,
        server_config_a2s.query_port,
        server_config_a2s.protocol,
        server_config_a2s.name,
    )

    fields = {f.name: f.value for f in embed.fields}
    assert fields["Story Progress"] == "42%"


@pytest.mark.asyncio
async def test_query_a2s_success_project_zomboid_adds_mod_fields(
    server_config_a2s, mock_a2s
):
    mock_a2s.info.game = "Project Zomboid"
    embed = main.ServerEmbed(server_config_a2s)

    await embed._query(
        server_config_a2s.query_host,
        server_config_a2s.query_port,
        server_config_a2s.protocol,
        server_config_a2s.name,
    )

    mods_field = next(f for f in embed.fields if f.name == "Mods")
    assert mods_field.inline is False
    fields = {f.name: f.value for f in embed.fields}
    assert fields["Mod Count"] == "3"
    assert fields["Mods"] == "Mod A;Mod B"


@pytest.mark.asyncio
async def test_query_a2s_failure_below_max_retries_sets_pending_and_increments_tries(
    server_config_a2s, mock_a2s, monkeypatch
):
    monkeypatch.setattr(main, "MAX_RETRIES", 3)
    mock_a2s.ainfo.side_effect = TimeoutError()

    embed = main.ServerEmbed(server_config_a2s, tries=0)
    await embed._query(
        server_config_a2s.query_host,
        server_config_a2s.query_port,
        server_config_a2s.protocol,
        server_config_a2s.name,
    )

    assert embed.status == main.ServerStatus.PENDING
    assert embed.tries == 1


@pytest.mark.asyncio
async def test_query_a2s_failure_reaches_max_retries_sets_offline(
    server_config_a2s, mock_a2s, monkeypatch
):
    monkeypatch.setattr(main, "MAX_RETRIES", 2)
    mock_a2s.ainfo.side_effect = ConnectionRefusedError()

    embed = main.ServerEmbed(server_config_a2s, tries=1)
    await embed._query(
        server_config_a2s.query_host,
        server_config_a2s.query_port,
        server_config_a2s.protocol,
        server_config_a2s.name,
    )

    assert embed.status == main.ServerStatus.OFFLINE
    assert embed.tries == 2


@pytest.mark.asyncio
async def test_query_a2s_failure_already_at_max_retries_stays_offline_without_incrementing(
    server_config_a2s, mock_a2s, monkeypatch
):
    monkeypatch.setattr(main, "MAX_RETRIES", 2)
    mock_a2s.ainfo.side_effect = OSError()

    embed = main.ServerEmbed(server_config_a2s, tries=2)
    await embed._query(
        server_config_a2s.query_host,
        server_config_a2s.query_port,
        server_config_a2s.protocol,
        server_config_a2s.name,
    )

    assert embed.status == main.ServerStatus.OFFLINE
    assert embed.tries == 2


@pytest.mark.asyncio
async def test_query_a2s_broken_message_error_is_handled_like_timeout(
    server_config_a2s, mock_a2s, monkeypatch
):
    monkeypatch.setattr(main, "MAX_RETRIES", 3)
    mock_a2s.ainfo.side_effect = a2s.BrokenMessageError("bad message")

    embed = main.ServerEmbed(server_config_a2s, tries=0)
    await embed._query(
        server_config_a2s.query_host,
        server_config_a2s.query_port,
        server_config_a2s.protocol,
        server_config_a2s.name,
    )

    assert embed.status == main.ServerStatus.PENDING
    assert embed.tries == 1


@pytest.mark.asyncio
async def test_query_unknown_protocol_sets_unqueried(server_config_factory):
    config = server_config_factory(
        embed_color="#ff0000", protocol=main.Protocol.MINECRAFT
    )
    embed = main.ServerEmbed(config)

    await embed._query(config.query_host, config.query_port, config.protocol, config.name)

    assert embed.status == main.ServerStatus.UNQUERIED
