import json
import os
import sys
from dataclasses import dataclass
from enum import Enum

import a2s
import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv

load_dotenv()

OUT_TMP = "./server_data.tmp.json"
OUT_SERVER_DATA = "./server_data.json"


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
    """
    The server embed should be built on init and update.
    Sketch of object lifecycle:
      1. ServerEmbed __init__ -> Build from server config
      2. Query periodically for server status
      3. If CURRENT ServerEmbed != NEW Query, NEW Query = ServerEmbed
      4. If destroyed, destroy ServerEmbed and unregister from server_data.json. 
         The admin shouldn't delete the embed via discord but from the app_command `Delete game server`
      5. If the embed ID doesn't exist, send a new embed (?)

    Open Questions brain dump:
      - What happens if a server doesn't need querying: `protocol = NONE` ?
      - How do we know which Servers to query?
      - Are we selective about server queries or is it cheap?
      - What differentates __init__ from build?
      - Does a ServerEmbed need to be rebuilt after every query?
        - Is it cheap or expensive?
    """
    ## TODO:= Resolve if needed -> **kwargs are for passing additional embed args without needing to enumerate them
    def __init__(self, config: ServerConfig, **kwargs):
        super().__init__()
        await self.build(config=config)

    async def query(self, address: str, port: int, protocol: Protocol):
        ## TODO:= Guards for A2S and verify query host is reachable
        if protocol == Protocol.A2S:
            query_endpoint = (address, port)
            info = a2s.info(query_endpoint)
            rules = a2s.rules(query_endpoint)
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

    async def build(self, config: ServerConfig):
        self.set_thumbnail(url=config.embed_icon)
        self.set_image(url=config.embed_image)

        self.add_field(name="Host", value=config.host)
        self.add_field(name="Port", value=config.port)
        self.add_field(name="Name", value=config.name)

        self.set_footer(text=f"{config.host}:{config.port}")

        self.query(config.query_host, config.query_port, config.protocol)

        if self.title is None:
            print("warn: the game title was not fetched")
            self.title = config.name


class ServerStore:
    def __init__(self):
        ## TODO:= Resolve if needed -> TypedDict of { ServerConfig } ?
        self.servers = {}
        try:
            with open(OUT_SERVER_DATA, "r") as f:
                self.servers = json.load(f)
                print("Found server config:\n", json.dumps(self.servers, indent=2))
        except FileNotFoundError:
            print("Initializing new server_data...")

    def __apply__(self):
        with open(OUT_TMP, "w") as f:
            json.dump(self.servers, f, indent=2)
        os.replace(OUT_TMP, OUT_SERVER_DATA)

    def delete(self, embed_id: str):
        self.servers.pop(embed_id)
        self.__apply__()

    def update(self, config: ServerConfig):
        if config.embed_id is None:
            print("Cannot update the server, has the embed been sent?")
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
        self.__apply__()


class Client(discord.Client):
    user: discord.ClientUser

    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        guild = discord.Object(id=os.getenv("GUILD_ID"))
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        self.channel = await self.fetch_channel(os.getenv("CHANNEL_ID"))
        self.query_loop.start()

    @tasks.loop(seconds=os.getenv("PING_INTERVAL") or 60)
    async def query_loop(self):
        for embed_id, config in server_store.servers.items():
            try:
                config = ServerConfig(**config)
                embed = await ServerEmbed(config)
                ## TODO:= Edit the embed (create if it doesn't exist)
                #message = await self.channel.send(embed)
                #await message.edit(embed=embed)
            ## TODO:= Blind exception for now, til I know which ones would actually occur
            except Exception as e:  # noqa: BLE001
                print(f"Failed to update {embed_id}, {config.name}: {e}")

    @query_loop.before_loop
    async def before_query_loop(self):
        await self.wait_until_ready()


if __name__ == "__main__":
    server_store = ServerStore()
    client = Client(intents=discord.Intents.default())

    @client.event
    async def on_ready():
        print(f"Logged in as {client.user} (ID: {client.user.id})")
        print("------")

    @client.tree.command(name="add-server", description="Register a game server")
    @app_commands.describe(
        host="Server IP or hostname",
        name="Display name",
        port="Connection port",
        protocol="Query protocol",
        query_host="Host used for status queries",
        query_port="Port used for status queries",
        embed_color="Hex embed color",
        embed_icon="URL to icon image",
        embed_image="URL to embed banner image",
    )
    async def add_server(
        interaction: discord.Interaction,
        host: str,
        name: str,
        port: int,
        protocol: Protocol,
        query_host: str,
        query_port: int,
        embed_color: str | None,
        embed_icon: str | None,
        embed_image: str | None,
    ):
        new_server = ServerConfig(
            host,
            name,
            port,
            protocol,
            query_host,
            query_port,
            embed_color,
            embed_icon,
            None,
            embed_image,
        )
        embed = ServerEmbed(new_server)
        message = await client.channel.send(embed=embed)
        new_server.embed_id = message.id
        server_store.update(new_server)

        await interaction.response.send_message(
            f"Successfully created {new_server.name}!", ephemeral=True
        )

    missing_envs = [
        e for e in ["BOT_TOKEN", "CHANNEL_ID", "GUILD_ID"] if not os.getenv(e)
    ]
    if missing_envs:
        print(f"Error: missing env vars {', '.join(missing_envs)}")
        sys.exit(1)

    client.run(os.getenv("BOT_TOKEN"))
