from unittest.mock import AsyncMock, Mock

import discord
import pytest

import main


# ---- query_loop / _poll_state -------------------------------------------------


@pytest.mark.asyncio
async def test_query_loop_first_pass_online_entry_edits_message_and_records_poll_state(
    client_instance, server_store, mock_a2s
):
    embed_id = "1535769672082002011"
    del server_store.servers["1535777208965136449"]
    fetched_message = Mock()
    fetched_message.edit = AsyncMock()
    client_instance.channel.fetch_message.return_value = fetched_message

    await client_instance.query_loop.coro(client_instance)

    tries, status = client_instance._poll_state[embed_id]
    assert status == main.ServerStatus.ONLINE
    client_instance.channel.fetch_message.assert_any_await(int(embed_id))
    fetched_message.edit.assert_called_once()


@pytest.mark.asyncio
async def test_query_loop_second_pass_same_status_skips_edit(
    client_instance, server_store, mock_a2s
):
    embed_id = "1535769672082002011"
    del server_store.servers["1535777208965136449"]
    client_instance._poll_state[embed_id] = (0, main.ServerStatus.ONLINE)

    await client_instance.query_loop.coro(client_instance)

    client_instance.channel.fetch_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_query_loop_transition_to_offline_triggers_edit_and_updates_poll_state(
    client_instance, server_store, mock_a2s, monkeypatch
):
    embed_id = "1535769672082002011"
    del server_store.servers["1535777208965136449"]
    monkeypatch.setattr(main, "MAX_RETRIES", 1)
    mock_a2s.ainfo.side_effect = TimeoutError()
    client_instance._poll_state[embed_id] = (0, main.ServerStatus.ONLINE)
    fetched_message = Mock()
    fetched_message.edit = AsyncMock()
    client_instance.channel.fetch_message.return_value = fetched_message

    await client_instance.query_loop.coro(client_instance)

    tries, status = client_instance._poll_state[embed_id]
    assert status == main.ServerStatus.OFFLINE
    assert tries == 1
    fetched_message.edit.assert_called_once()


@pytest.mark.asyncio
async def test_query_loop_repeated_pending_failure_does_not_re_edit(
    client_instance, server_store, mock_a2s, monkeypatch
):
    embed_id = "1535769672082002011"
    del server_store.servers["1535777208965136449"]
    monkeypatch.setattr(main, "MAX_RETRIES", 3)
    mock_a2s.ainfo.side_effect = TimeoutError()
    client_instance._poll_state[embed_id] = (1, main.ServerStatus.PENDING)

    await client_instance.query_loop.coro(client_instance)

    tries, status = client_instance._poll_state[embed_id]
    assert status == main.ServerStatus.PENDING
    assert tries == 2
    client_instance.channel.fetch_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_query_loop_message_not_found_recreates_and_rekeys_poll_state(
    client_instance, server_store, mock_a2s
):
    old_embed_id = "1535769672082002011"
    del server_store.servers["1535777208965136449"]
    client_instance.channel.fetch_message.side_effect = discord.NotFound(
        Mock(status=404, reason="Not Found"), "Unknown Message"
    )
    new_message = Mock()
    new_message.id = 7777777777777777777
    client_instance.channel.send.return_value = new_message

    await client_instance.query_loop.coro(client_instance)

    assert old_embed_id not in server_store.servers
    assert old_embed_id not in client_instance._poll_state
    assert str(new_message.id) in server_store.servers
    assert str(new_message.id) in client_instance._poll_state
    client_instance.channel.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_query_loop_unqueried_protocol_none_entry_edits_once_then_stabilizes(
    client_instance, server_store
):
    embed_id = "1535777208965136449"
    del server_store.servers["1535769672082002011"]
    fetched_message = Mock()
    fetched_message.edit = AsyncMock()
    client_instance.channel.fetch_message.return_value = fetched_message

    await client_instance.query_loop.coro(client_instance)
    assert client_instance._poll_state[embed_id][1] == main.ServerStatus.UNQUERIED
    fetched_message.edit.assert_called_once()

    client_instance.channel.fetch_message.reset_mock()
    await client_instance.query_loop.coro(client_instance)
    client_instance.channel.fetch_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_query_loop_bad_entry_does_not_abort_remaining_entries(
    client_instance, server_store
):
    server_store.servers["1535769672082002011"]["protocol"] = "NotAProtocol"
    fetched_message = Mock()
    fetched_message.edit = AsyncMock()
    client_instance.channel.fetch_message.return_value = fetched_message

    await client_instance.query_loop.coro(client_instance)

    assert "1535777208965136449" in client_instance._poll_state
    fetched_message.edit.assert_called_once()


@pytest.mark.asyncio
async def test_query_loop_http_exception_during_message_edit_is_caught(
    client_instance, server_store
):
    fetched_message = Mock()
    fetched_message.edit = Mock(
        side_effect=discord.HTTPException(
            Mock(status=500, reason="Internal Server Error"), "boom"
        )
    )
    client_instance.channel.fetch_message.return_value = fetched_message

    await client_instance.query_loop.coro(client_instance)


# ---- add_server ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_server_success_none_protocol_creates_and_stores_embed(
    empty_server_store, patched_client_channel, fake_interaction
):
    await main.add_server.callback(
        fake_interaction,
        name="New Server",
        host="new.host",
        port=1234,
        protocol=main.Protocol.NONE,
        query_host=None,
        query_port=None,
        embed_color=None,
        embed_image=None,
        embed_thumbnail=None,
    )

    patched_client_channel.send.assert_awaited_once()
    assert len(empty_server_store.servers) == 1
    fake_interaction.followup.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_add_server_missing_query_fields_for_non_none_protocol_sends_error(
    empty_server_store, patched_client_channel, fake_interaction
):
    await main.add_server.callback(
        fake_interaction,
        name="New Server",
        host="new.host",
        port=1234,
        protocol=main.Protocol.A2S,
        query_host=None,
        query_port=None,
        embed_color=None,
        embed_image=None,
        embed_thumbnail=None,
    )

    fake_interaction.followup.send.assert_awaited_once()
    patched_client_channel.send.assert_not_awaited()
    assert empty_server_store.servers == {}


@pytest.mark.asyncio
async def test_add_server_invalid_embed_color_sends_error(
    empty_server_store, patched_client_channel, fake_interaction
):
    await main.add_server.callback(
        fake_interaction,
        name="New Server",
        host="new.host",
        port=1234,
        protocol=main.Protocol.NONE,
        query_host=None,
        query_port=None,
        embed_color="not-a-color",
        embed_image=None,
        embed_thumbnail=None,
    )

    sent_message = fake_interaction.followup.send.await_args.args[0]
    assert "not a valid embed color" in sent_message
    patched_client_channel.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_add_server_invalid_embed_image_url_sends_error(
    empty_server_store, patched_client_channel, fake_interaction
):
    await main.add_server.callback(
        fake_interaction,
        name="New Server",
        host="new.host",
        port=1234,
        protocol=main.Protocol.NONE,
        query_host=None,
        query_port=None,
        embed_color=None,
        embed_image="not-a-url",
        embed_thumbnail=None,
    )

    fake_interaction.followup.send.assert_awaited_once()
    patched_client_channel.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_add_server_a2s_success_with_query_fields(
    empty_server_store, patched_client_channel, fake_interaction, mock_a2s
):
    await main.add_server.callback(
        fake_interaction,
        name="New Server",
        host="new.host",
        port=1234,
        protocol=main.Protocol.A2S,
        query_host="10.0.0.1",
        query_port=27015,
        embed_color="#ff0000",
        embed_image=None,
        embed_thumbnail=None,
    )

    stored = next(iter(empty_server_store.servers.values()))
    assert stored["protocol"] == "A2S"
    assert stored["query_host"] == "10.0.0.1"


# ---- context-menu commands ------------------------------------------------------


@pytest.mark.asyncio
async def test_edit_server_connection_untracked_sends_not_a_server_message(
    server_store, fake_message_factory, fake_interaction
):
    message = fake_message_factory(999999999999999999)
    await main.edit_server_connection.callback(fake_interaction, message)

    fake_interaction.response.send_message.assert_awaited_once_with(
        main._NOT_A_SERVER_EMBED, ephemeral=True
    )


@pytest.mark.asyncio
async def test_edit_server_connection_tracked_sends_modal(
    server_store, fake_message_factory, fake_interaction
):
    message = fake_message_factory(1535769672082002011)
    await main.edit_server_connection.callback(fake_interaction, message)

    fake_interaction.response.send_modal.assert_awaited_once()
    sent_modal = fake_interaction.response.send_modal.await_args.args[0]
    assert isinstance(sent_modal, main.EditConnectionModal)


@pytest.mark.asyncio
async def test_edit_server_display_untracked_sends_not_a_server_message(
    server_store, fake_message_factory, fake_interaction
):
    message = fake_message_factory(999999999999999999)
    await main.edit_server_display.callback(fake_interaction, message)

    fake_interaction.response.send_message.assert_awaited_once_with(
        main._NOT_A_SERVER_EMBED, ephemeral=True
    )


@pytest.mark.asyncio
async def test_edit_server_display_tracked_sends_modal(
    server_store, fake_message_factory, fake_interaction
):
    message = fake_message_factory(1535769672082002011)
    await main.edit_server_display.callback(fake_interaction, message)

    sent_modal = fake_interaction.response.send_modal.await_args.args[0]
    assert isinstance(sent_modal, main.EditDisplayModal)


@pytest.mark.asyncio
async def test_delete_game_server_untracked_sends_not_a_server_message(
    server_store, fake_message_factory, fake_interaction
):
    message = fake_message_factory(999999999999999999)
    await main.delete_game_server.callback(fake_interaction, message)

    fake_interaction.response.send_message.assert_awaited_once_with(
        main._NOT_A_SERVER_EMBED, ephemeral=True
    )


@pytest.mark.asyncio
async def test_delete_game_server_tracked_sends_modal(
    server_store, fake_message_factory, fake_interaction
):
    message = fake_message_factory(1535769672082002011)
    await main.delete_game_server.callback(fake_interaction, message)

    sent_modal = fake_interaction.response.send_modal.await_args.args[0]
    assert isinstance(sent_modal, main.DeleteServerModal)


@pytest.mark.asyncio
async def test_add_to_server_store_already_tracked_sends_already_tracked_message(
    server_store, fake_message_factory, fake_interaction
):
    message = fake_message_factory(1535769672082002011)
    await main.add_to_server_store.callback(fake_interaction, message)

    fake_interaction.response.send_message.assert_awaited_once()
    sent_message = fake_interaction.response.send_message.await_args.args[0]
    assert "already a tracked server" in sent_message


@pytest.mark.asyncio
async def test_add_to_server_store_no_embeds_sends_not_a_server_message(
    server_store, fake_message_factory, fake_interaction
):
    message = fake_message_factory(999999999999999999, embeds=[])
    await main.add_to_server_store.callback(fake_interaction, message)

    fake_interaction.response.send_message.assert_awaited_once_with(
        main._NOT_A_SERVER_EMBED, ephemeral=True
    )


@pytest.mark.asyncio
async def test_add_to_server_store_unparseable_embed_sends_config_error_message(
    server_store, fake_message_factory, fake_interaction
):
    bad_embed = discord.Embed()
    bad_embed.add_field(name="Host", value="h")
    message = fake_message_factory(999999999999999999, embeds=[bad_embed])

    await main.add_to_server_store.callback(fake_interaction, message)

    sent_message = fake_interaction.response.send_message.await_args.args[0]
    assert "doesn't look like a server config" in sent_message


@pytest.mark.asyncio
async def test_add_to_server_store_valid_embed_sends_modal(
    server_store, fake_message_factory, fake_interaction
):
    good_embed = discord.Embed()
    good_embed.add_field(name="Host", value="h")
    good_embed.add_field(name="Port", value="1234")
    good_embed.add_field(name="Name", value="n")
    message = fake_message_factory(999999999999999999, embeds=[good_embed])

    await main.add_to_server_store.callback(fake_interaction, message)

    fake_interaction.response.send_modal.assert_awaited_once()
    sent_modal = fake_interaction.response.send_modal.await_args.args[0]
    assert isinstance(sent_modal, main.AddServerFromEmbedModal)
