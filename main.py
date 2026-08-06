import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

import a2s
import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv

load_dotenv()

OUT_TMP = "./server_data.tmp.json"
OUT_SERVER_DATA = "./server_data.json"

discord.utils.setup_logging(
    level=os.getenv("LOG_LEVEL", "INFO"),
    root=True,
)

logger = logging.getLogger(__name__)
logging.getLogger("discord.client").setLevel(logging.ERROR)


class Protocol(Enum):
    A2S = "a2s"
    MC_QUERY = "minecraft_query"
    NONE = "none"


@dataclass
class ServerConfig:
    host: str
    name: str
    port: int
    protocol: Protocol
    query_host: str
    query_port: int
    embed_color: discord.Color
    embed_icon: str | None
    embed_id: str | None  ## none until the embed is sent
    embed_image: str | None


class ServerEmbed(discord.Embed):
    def __init__(self, config: ServerConfig):
        super().__init__()

        ## TODO:= Maybe we shouldn't throw away the config
        ##        and instead keep save it as self.config?
        ##        This issue crops up in _query where warn does not know embed_id

        self.add_field(name="Host", value=config.host)
        self.add_field(name="Port", value=config.port)
        self.add_field(name="Name", value=config.name)

        self.set_footer(icon_url=config.embed_icon, text=f"{config.host}:{config.port}")

        self.set_image(url=config.embed_image)

        self.timestamp = datetime.now(timezone.utc)

    @classmethod
    async def build(cls, config: ServerConfig):
        self = cls(config)
        await self._query(config.query_host, config.query_port, config.protocol)
        if self.title is None:
            logger.warning("The game title was not fetched")
            self.title = config.name
        return self

    async def _query(self, address: str, port: int, protocol: Protocol):
        if protocol == Protocol.NONE:
            return
        elif protocol == Protocol.A2S:
            query_endpoint = (address, port)
            try:
                info = await a2s.ainfo(query_endpoint)
                rules = await a2s.arules(query_endpoint)
            except (
                TimeoutError,
                ConnectionRefusedError,
                OSError,
                a2s.BrokenMessageError,
            ) as e:
                logger.warning(f"a2s: Failed to query {address}:{port} : {e}")
                return

            self.timestamp = datetime.now(timezone.utc)
            self.title = info.game
            self.add_field(
                name="Players",
                value=f"{info.player_count!s}/{info.max_players!s}",
            )
            self.add_field(name="Game Version", value=info.version)
            if info.game == "Abiotic Factor":
                self.add_field(name="Story Progress", value=rules["StoryProgress_s"])
            if info.game == "Project Zomboid":
                self.add_field(name="Mod Count", value=rules["mod_count"])
                self.add_field(name="Mods", value=rules["mods"])
            logger.debug(
                f"{address}:{port} ok: {info.game}, {info.player_count!s}/{info.max_players!s}"
            )
        else:
            logger.warning("The protocol for host {address} is unknown")


class ServerStore:
    def __init__(self):
        self.servers = {}
        try:
            with open(OUT_SERVER_DATA, "r") as f:
                self.servers = json.load(f)
                logger.info(
                    f"Found server config:\n {json.dumps(self.servers, indent=2)}"
                )
        except FileNotFoundError:
            logger.info("Initializing new server_data...")

    def _apply(self):
        with open(OUT_TMP, "w") as f:
            json.dump(self.servers, f, indent=2)
        os.replace(OUT_TMP, OUT_SERVER_DATA)

    def delete(self, embed_id: str):
        self.servers.pop(embed_id)
        self._apply()

    def update(self, config: ServerConfig):
        if config.embed_id is None:
            print("Cannot update the server, has the embed been sent?")
            ## TODO:= Prompt if the user wants to create a server
            ##        or show saved info to create new server
            return
        self.servers[str(config.embed_id)] = {
            "host": config.host,
            "name": config.name,
            "port": str(config.port),
            "query_host": config.query_host,
            "query_port": str(config.query_port),
            "protocol": config.protocol.value,
            "embed_color": config.embed_color,
            "embed_icon": config.embed_icon,
            "embed_id": config.embed_id,
            "embed_image": config.embed_image,
        }
        self._apply()


class Client(discord.Client):
    user: discord.ClientUser

    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        guild = discord.Object(id=int(os.getenv("GUILD_ID")))
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        self.channel = await self.fetch_channel(int(os.getenv("CHANNEL_ID")))
        self.query_loop.start()

    @tasks.loop(seconds=int(os.getenv("PING_INTERVAL", 60)))
    async def query_loop(self):
        for embed_id, attrs in list(server_store.servers.items()):
            try:
                config = ServerConfig(
                    host=attrs["host"],
                    name=attrs["name"],
                    port=int(attrs["port"]),
                    protocol=Protocol(attrs["protocol"]),
                    query_host=attrs["query_host"],
                    query_port=int(attrs["query_port"]),
                    embed_color=attrs["embed_color"],
                    embed_icon=attrs["embed_icon"],
                    embed_id=attrs["embed_id"],
                    embed_image=attrs["embed_image"],
                )
                embed = await ServerEmbed.build(config)
                try:
                    message = await self.channel.fetch_message(int(attrs["embed_id"]))
                    await message.edit(embed=embed)
                except discord.NotFound:
                    message = await self.channel.send(embed=embed)
                    server_store.delete(embed_id)
                    config.embed_id = message.id
                    server_store.update(config)
            except (discord.HTTPException, KeyError, TypeError, ValueError) as e:
                logger.error(
                    f"Failed to update {embed_id} {attrs.get('name', '?')}: {e}"
                )

    @query_loop.before_loop
    async def before_query_loop(self):
        await self.wait_until_ready()


client = Client(intents=discord.Intents.default())


@client.event
async def on_ready():
    logger.info(f"Logged in as {client.user} (ID: {client.user.id})")


@client.tree.command(name="add-server", description="Register a game server")
@app_commands.describe(
    name="Display name",
    host="Server IP or hostname",
    port="Connection port",
    protocol="Query protocol",
    query_host="Host used for game query",
    query_port="Port used for game  query",
    embed_color="Hex embed color",
    embed_icon="URL to icon image",
    embed_image="URL to embed banner image",
)
async def add_server(
    interaction: discord.Interaction,
    name: str,
    host: str,
    port: int,
    protocol: Protocol,
    query_host: str,
    query_port: int,
    embed_color: str | None,
    embed_icon: str | None,
    embed_image: str | None,
):
    new_server = ServerConfig(
        host=host,
        name=name,
        port=port,
        protocol=protocol,
        query_host=query_host,
        query_port=query_port,
        embed_color=embed_color,
        embed_icon=embed_icon,
        embed_id=None,
        embed_image=embed_image,
    )
    embed = await ServerEmbed.build(new_server)
    message = await client.channel.send(embed=embed)
    new_server.embed_id = message.id
    server_store.update(new_server)

    await interaction.response.send_message(
        f"Successfully created {new_server.name}!", ephemeral=True
    )


## TODO:= Edit, Delete Server right-click action

if __name__ == "__main__":
    server_store = ServerStore()

    missing_envs = [
        e for e in ["BOT_TOKEN", "CHANNEL_ID", "GUILD_ID"] if not os.getenv(e)
    ]
    if missing_envs:
        logger.error(f"Error: missing env vars {', '.join(missing_envs)}")
        sys.exit(1)

    client.run(os.getenv("BOT_TOKEN"), log_handler=None)
