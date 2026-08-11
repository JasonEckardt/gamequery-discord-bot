from unittest.mock import Mock

import discord
import pytest

import main
from conftest import set_select_value, set_text_value


# ---- EditConnectionModal -----------------------------------------------------


def test_edit_connection_modal_init_raises_if_message_untracked(
    server_store, fake_message_factory
):
    message = fake_message_factory(999999999999999999)
    with pytest.raises(ValueError):
        main.EditConnectionModal(server_store, message)


def test_edit_connection_modal_init_prefills_fields_from_store(
    server_store, fake_message_factory
):
    message = fake_message_factory(1535769672082002011)
    modal = main.EditConnectionModal(server_store, message)

    stored = server_store.servers["1535769672082002011"]
    assert modal.host.component.default == str(stored["host"])
    assert modal.port.component.default == str(stored["port"])
    assert modal.query_host.component.default == str(stored["query_host"])
    assert modal.query_port.component.default == str(stored["query_port"])

    default_options = [o for o in modal.protocol.component.options if o.default]
    assert len(default_options) == 1
    assert default_options[0].value == stored["protocol"]


@pytest.mark.asyncio
async def test_edit_connection_modal_on_submit_success_updates_store_and_edits_message(
    server_store, fake_message_factory, fake_interaction
):
    message = fake_message_factory(1535769672082002011)
    modal = main.EditConnectionModal(server_store, message)

    set_text_value(modal.host, "new.host")
    set_text_value(modal.port, "9999")
    set_text_value(modal.query_host, "10.0.0.1")
    set_text_value(modal.query_port, "27020")
    set_select_value(modal.protocol, "A2S")

    await modal.on_submit(fake_interaction)

    updated = server_store.servers["1535769672082002011"]
    assert updated["host"] == "new.host"
    assert updated["port"] == 9999
    assert updated["query_port"] == 27020
    message.edit.assert_awaited_once()
    assert "embed" in message.edit.await_args.kwargs
    fake_interaction.followup.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_edit_connection_modal_on_submit_invalid_port_sends_error_without_updating(
    server_store, fake_message_factory, fake_interaction
):
    message = fake_message_factory(1535769672082002011)
    modal = main.EditConnectionModal(server_store, message)
    before = dict(server_store.servers["1535769672082002011"])

    set_text_value(modal.host, "new.host")
    set_text_value(modal.port, "not-a-number")
    set_text_value(modal.query_host, "10.0.0.1")
    set_text_value(modal.query_port, "27020")
    set_select_value(modal.protocol, "A2S")

    await modal.on_submit(fake_interaction)

    fake_interaction.followup.send.assert_awaited_once()
    assert server_store.servers["1535769672082002011"] == before
    message.edit.assert_not_awaited()


# ---- EditDisplayModal ---------------------------------------------------------


def test_edit_display_modal_init_raises_if_message_untracked(
    server_store, fake_message_factory
):
    message = fake_message_factory(999999999999999999)
    with pytest.raises(ValueError):
        main.EditDisplayModal(server_store, message)


def test_edit_display_modal_init_prefills_fields_including_empty_string_for_none(
    server_store, fake_message_factory
):
    message = fake_message_factory(1535777208965136449)
    modal = main.EditDisplayModal(server_store, message)

    assert modal.embed_image.component.default == ""
    assert modal.embed_thumbnail.component.default == ""
    assert modal.name.component.default == "Test"


@pytest.mark.asyncio
async def test_edit_display_modal_on_submit_success_sanitizes_and_updates(
    server_store, fake_message_factory, fake_interaction
):
    message = fake_message_factory(1535777208965136449)
    modal = main.EditDisplayModal(server_store, message)

    set_text_value(modal.name, "Renamed")
    set_text_value(modal.embed_color, "ff0000")
    set_text_value(modal.embed_image, "")
    set_text_value(modal.embed_thumbnail, "")

    await modal.on_submit(fake_interaction)

    updated = server_store.servers["1535777208965136449"]
    assert updated["name"] == "Renamed"
    assert updated["embed_color"] == "#ff0000"
    message.edit.assert_awaited_once()
    fake_interaction.followup.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_edit_display_modal_on_submit_invalid_embed_color_sends_error(
    server_store, fake_message_factory, fake_interaction
):
    message = fake_message_factory(1535777208965136449)
    modal = main.EditDisplayModal(server_store, message)
    before = dict(server_store.servers["1535777208965136449"])

    set_text_value(modal.name, "Renamed")
    set_text_value(modal.embed_color, "not-a-color")

    await modal.on_submit(fake_interaction)

    sent_message = fake_interaction.followup.send.await_args.args[0]
    assert "not a valid embed color" in sent_message
    assert server_store.servers["1535777208965136449"] == before
    message.edit.assert_not_awaited()


@pytest.mark.asyncio
async def test_edit_display_modal_on_submit_invalid_url_sends_error(
    server_store, fake_message_factory, fake_interaction
):
    message = fake_message_factory(1535777208965136449)
    modal = main.EditDisplayModal(server_store, message)
    before = dict(server_store.servers["1535777208965136449"])

    set_text_value(modal.name, "Renamed")
    set_text_value(modal.embed_color, "")
    set_text_value(modal.embed_image, "not-a-url")

    await modal.on_submit(fake_interaction)

    fake_interaction.followup.send.assert_awaited_once()
    assert server_store.servers["1535777208965136449"] == before
    message.edit.assert_not_awaited()


# ---- DeleteServerModal --------------------------------------------------------


def test_delete_server_modal_init_raises_if_message_untracked(
    server_store, fake_message_factory
):
    message = fake_message_factory(999999999999999999)
    with pytest.raises(ValueError):
        main.DeleteServerModal(server_store, message)


def test_delete_server_modal_init_sets_placeholder_to_stored_name(
    server_store, fake_message_factory
):
    message = fake_message_factory(1535777208965136449)
    modal = main.DeleteServerModal(server_store, message)

    assert modal.name.component.placeholder == "Test"


@pytest.mark.asyncio
async def test_delete_server_modal_on_submit_name_mismatch_cancels_without_deleting(
    server_store, fake_message_factory, fake_interaction
):
    message = fake_message_factory(1535777208965136449)
    modal = main.DeleteServerModal(server_store, message)

    set_text_value(modal.name, "Wrong Name")
    await modal.on_submit(fake_interaction)

    assert "1535777208965136449" in server_store.servers
    message.delete.assert_not_awaited()
    sent_message = fake_interaction.followup.send.await_args.args[0]
    assert "Deletion cancelled" in sent_message


@pytest.mark.asyncio
async def test_delete_server_modal_on_submit_name_match_deletes_entry_and_message(
    server_store, fake_message_factory, fake_interaction
):
    message = fake_message_factory(1535777208965136449)
    modal = main.DeleteServerModal(server_store, message)

    set_text_value(modal.name, "Test")
    await modal.on_submit(fake_interaction)

    assert "1535777208965136449" not in server_store.servers
    message.delete.assert_awaited_once()
    fake_interaction.followup.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_server_modal_on_submit_swallows_already_deleted_message(
    server_store, fake_message_factory, fake_interaction
):
    message = fake_message_factory(1535777208965136449)
    modal = main.DeleteServerModal(server_store, message)
    message.delete.side_effect = discord.NotFound(
        Mock(status=404, reason="Not Found"), "Unknown Message"
    )

    set_text_value(modal.name, "Test")
    await modal.on_submit(fake_interaction)

    assert "1535777208965136449" not in server_store.servers
    fake_interaction.followup.send.assert_awaited_once()


# ---- AddServerFromEmbedModal --------------------------------------------------


def _parsed_config(**overrides):
    defaults = dict(
        host="parsed.host",
        name="Parsed Server",
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


def test_add_from_embed_modal_defaults_protocol_option_to_none(
    server_store, fake_message_factory
):
    message = fake_message_factory(1234567890123456789)
    modal = main.AddServerFromEmbedModal(server_store, message, _parsed_config())

    defaults = {o.value: o.default for o in modal.protocol.component.options}
    assert defaults[main.Protocol.NONE.value] is True
    assert defaults[main.Protocol.A2S.value] is False


@pytest.mark.asyncio
async def test_add_from_embed_modal_on_submit_protocol_none_success(
    server_store, fake_message_factory, fake_interaction
):
    message = fake_message_factory(1234567890123456789)
    modal = main.AddServerFromEmbedModal(server_store, message, _parsed_config())

    set_select_value(modal.protocol, "None")
    set_text_value(modal.query_host, "")
    set_text_value(modal.query_port, "")

    await modal.on_submit(fake_interaction)

    stored = server_store.servers["1234567890123456789"]
    assert stored["query_host"] is None
    assert stored["query_port"] is None
    message.edit.assert_awaited_once()
    fake_interaction.followup.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_add_from_embed_modal_on_submit_a2s_missing_query_fields_sends_error(
    server_store, fake_message_factory, fake_interaction
):
    message = fake_message_factory(1234567890123456789)
    modal = main.AddServerFromEmbedModal(server_store, message, _parsed_config())

    set_select_value(modal.protocol, "A2S")
    set_text_value(modal.query_host, "")
    set_text_value(modal.query_port, "")

    await modal.on_submit(fake_interaction)

    fake_interaction.followup.send.assert_awaited_once()
    assert "1234567890123456789" not in server_store.servers
    message.edit.assert_not_awaited()


@pytest.mark.asyncio
async def test_add_from_embed_modal_on_submit_a2s_invalid_query_port_sends_error(
    server_store, fake_message_factory, fake_interaction
):
    message = fake_message_factory(1234567890123456789)
    modal = main.AddServerFromEmbedModal(server_store, message, _parsed_config())

    set_select_value(modal.protocol, "A2S")
    set_text_value(modal.query_host, "10.0.0.1")
    set_text_value(modal.query_port, "abc")

    await modal.on_submit(fake_interaction)

    sent_message = fake_interaction.followup.send.await_args.args[0]
    assert "whole number" in sent_message
    assert "1234567890123456789" not in server_store.servers


@pytest.mark.asyncio
async def test_add_from_embed_modal_on_submit_a2s_success(
    server_store, fake_message_factory, fake_interaction, mock_a2s
):
    message = fake_message_factory(1234567890123456789)
    modal = main.AddServerFromEmbedModal(
        server_store, message, _parsed_config(embed_color="#ff0000")
    )

    set_select_value(modal.protocol, "A2S")
    set_text_value(modal.query_host, "10.0.0.1")
    set_text_value(modal.query_port, "27015")

    await modal.on_submit(fake_interaction)

    stored = server_store.servers["1234567890123456789"]
    assert stored["protocol"] == "A2S"
    assert stored["query_host"] == "10.0.0.1"
    assert stored["query_port"] == 27015
    message.edit.assert_awaited_once()


# ---- pure helper functions ---------------------------------------------------


def test_sanitize_embed_color_returns_none_for_falsy():
    assert main._sanitize_embed_color(None) is None
    assert main._sanitize_embed_color("") is None


def test_sanitize_embed_color_prefixes_hash_when_missing():
    assert main._sanitize_embed_color("ff0000") == "#ff0000"


def test_sanitize_embed_color_raises_for_invalid_color():
    with pytest.raises(ValueError):
        main._sanitize_embed_color("not-a-color")


def test_sanitize_embed_url_returns_none_for_falsy():
    assert main._sanitize_embed_url(None) is None
    assert main._sanitize_embed_url("") is None


def test_sanitize_embed_url_raises_for_non_http_scheme_or_missing_netloc():
    with pytest.raises(ValueError):
        main._sanitize_embed_url("ftp://example.com/x.png")
    with pytest.raises(ValueError):
        main._sanitize_embed_url("not-a-url")


def test_parse_server_embed_returns_none_when_required_field_missing():
    embed = discord.Embed()
    embed.add_field(name="Host", value="h")
    embed.add_field(name="Name", value="n")
    assert main._parse_server_embed(embed) is None


def test_parse_server_embed_returns_none_when_port_not_int_parseable():
    embed = discord.Embed()
    embed.add_field(name="Host", value="h")
    embed.add_field(name="Port", value="not-a-number")
    embed.add_field(name="Name", value="n")
    assert main._parse_server_embed(embed) is None


def test_parse_server_embed_builds_config_from_valid_embed():
    embed = discord.Embed(color=discord.Color.from_str("#ff0000"))
    embed.add_field(name="Host", value="h")
    embed.add_field(name="Port", value="1234")
    embed.add_field(name="Name", value="n")
    embed.set_image(url="https://example.com/img.png")

    config = main._parse_server_embed(embed)

    assert config.host == "h"
    assert config.port == 1234
    assert config.name == "n"
    assert config.protocol == main.Protocol.NONE
    assert config.embed_image == "https://example.com/img.png"
    assert config.embed_color == str(embed.color)
