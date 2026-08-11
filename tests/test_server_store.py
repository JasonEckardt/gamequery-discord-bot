import json
import os

import pytest

import main


def test_init_with_no_existing_file_starts_empty(empty_store):
    assert empty_store.servers == {}


def test_init_loads_seeded_fixture_data(seeded_store):
    assert set(seeded_store.servers.keys()) == {
        "1535777208965136449",
        "1535769672082002011",
    }
    assert seeded_store.servers["1535777208965136449"]["host"] == "Test"
    assert seeded_store.servers["1535769672082002011"]["host"] == "lngs.lambdastack.org"


def test_loaded_entries_construct_valid_server_config(seeded_store):
    for embed_id, attrs in seeded_store.servers.items():
        config = main.ServerConfig(
            host=attrs["host"],
            name=attrs["name"],
            port=attrs["port"],
            protocol=main.Protocol(attrs["protocol"]),
            query_host=attrs["query_host"],
            query_port=attrs["query_port"],
            embed_color=attrs["embed_color"],
            embed_id=attrs["embed_id"],
            embed_image=attrs["embed_image"],
            embed_thumbnail=attrs["embed_thumbnail"],
        )
        assert config.host == attrs["host"]
        assert config.name == attrs["name"]
        assert str(config.embed_id) == embed_id


def test_update_writes_new_entry_and_persists(seeded_store):
    new_config = main.ServerConfig(
        host="new.host",
        name="New Server",
        port=27016,
        protocol=main.Protocol.NONE,
        query_host=None,
        query_port=None,
        embed_color="#00ff00",
        embed_id="1111111111111111111",
        embed_image=None,
        embed_thumbnail=None,
    )

    seeded_store.update(new_config)

    reloaded = main.ServerStore()
    assert reloaded.servers["1111111111111111111"]["host"] == "new.host"
    assert reloaded.servers["1111111111111111111"]["port"] == 27016
    assert reloaded.servers["1111111111111111111"]["protocol"] == "None"


def test_update_overwrites_existing_entry(seeded_store):
    updated_config = main.ServerConfig(
        host="changed.host",
        name="Abiotic Gamer",
        port=8888,
        protocol=main.Protocol.A2S,
        query_host="10.0.3.108",
        query_port=27015,
        embed_color="#a6ffff",
        embed_id="1535769672082002011",
        embed_image=None,
        embed_thumbnail=None,
    )

    seeded_store.update(updated_config)

    reloaded = main.ServerStore()
    assert len(reloaded.servers) == 2
    assert reloaded.servers["1535769672082002011"]["host"] == "changed.host"
    assert reloaded.servers["1535769672082002011"]["port"] == 8888


def test_update_with_embed_id_none_is_noop(seeded_store):
    before = json.loads(json.dumps(seeded_store.servers))

    noop_config = main.ServerConfig(
        host="ignored",
        name="ignored",
        port=1,
        protocol=main.Protocol.NONE,
        query_host=None,
        query_port=None,
        embed_color=None,
        embed_id=None,
        embed_image=None,
        embed_thumbnail=None,
    )
    seeded_store.update(noop_config)

    assert seeded_store.servers == before


def test_delete_removes_entry_and_persists(seeded_store):
    seeded_store.delete("1535777208965136449")

    reloaded = main.ServerStore()
    assert "1535777208965136449" not in reloaded.servers
    assert "1535769672082002011" in reloaded.servers


def test_delete_missing_key_raises_keyerror(seeded_store):
    with pytest.raises(KeyError):
        seeded_store.delete("nonexistent-id")


def test_apply_writes_valid_indented_json_readable_without_serverstore(seeded_store):
    seeded_store.delete("1535777208965136449")

    with open(main.OUT_SERVER_DATA) as f:
        raw = json.load(f)

    assert raw == seeded_store.servers


def test_out_tmp_file_is_replaced_not_left_behind(seeded_store, tmp_path):
    seeded_store.delete("1535777208965136449")

    assert not os.path.exists(main.OUT_TMP)
