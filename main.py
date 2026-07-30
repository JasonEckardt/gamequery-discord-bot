import json
import os
from dataclasses import dataclass
from enum import Enum

import a2s
import discord
from discord import app_commands
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
    embed_icon: str
    embed_id: str
    embed_image: str


class ServerEmbed(discord.Embed):
    ## TODO:= Resolve if needed -> **kwargs are for passing additional embed args without needing to enumerate them
    def __init__(self, config: ServerConfig, **kwargs):
        #super().__init__(color=config.color, **kwargs)
        super().__init__()

        self.set_thumbnail(url=config.embed_icon)
        self.set_image(url=config.embed_image)

        self.add_field(name="Host", value=config.host)
        self.add_field(name="Port", value=config.port)
        self.add_field(name="Name", value=config.name)

        self.set_footer(text=f"{config.host}:{config.port}")

        if config.protocol == Protocol.A2S:
            query = (config.query_host, config.query_port)
            info = a2s.info(query)
            rules = a2s.rules(query)
            self.title = info.game
            self.add_field(name="Players", value=f"{str(info.player_count)}/{str(info.max_players)}")
            self.add_field(name="Game Version", value=info.version)
            if info.game == "Abiotic Factor":
                self.add_field(name="Hardcore", value=rules["Hardcore_b"])
                self.add_field(name="Story Progress", value=rules["StoryProgress_s"])
            if info.game == "Project Zomboid":
                self.add_field(name="Mod Count", value=rules["mod_count"])
                self.add_field(name="Mods", value=rules["mods"])
        if self.title == None:
            print("warn: the game title was not fetched")
            self.title = config.name

    async def send(self, interaction: discord.Interaction, config: ServerConfig):
        message = await client.channel.send(embed=self)
        ServerStore.update(config)


class ServerStore:
    def __init__(self):
        ## TODO:= Resolve if needed -> TypedDict of { ServerConfig } ?
        self.servers = {}
        try:
            with open(OUT_SERVER_DATA, 'r') as f:
                self.servers = json.load(f)
                print("Found server config:\n", json.dumps(self.servers, indent=2))
        except FileNotFoundError:
            print("Initializing new server_data...")

    def __apply__(self):
        with open(OUT_TMP, 'w') as f:
            json.dump(self.servers, f, indent=2)
        os.replace(OUT_TMP, OUT_SERVER_DATA)

    def delete(self, embed_id: str):
        self.servers.pop(embed_id)
        self.__apply__()

    def update(self, config: ServerConfig):
        self.servers[str(config.embed_id)] = {
            "host": config.host,
            "name": config.name,
            "port": str(config.port),
            "query_host": config.query_host,
            "query_port": str(config.query_port),
            "protocol": config.protocol.value,
            "embed_color": config.embed_icon,
            "embed_icon": config.embed_icon,
            "embed_image": config.embed_image
        }
        self.__apply__()

class Client(discord.Client):
    user: discord.ClientUser

    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        self.channel = None
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        self.tree.copy_global_to(guild=os.getenv("GUILD_ID"))
        await self.tree.sync(guild=os.getenv("GUILD_ID"))
        self.channel = await self.fetch_channel(os.getenv("CHANNEL_ID"))


intents = discord.Intents.default()
client = Client(intents=intents)


@client.event
async def on_ready():
    print(f"Logged in as {client.user} (ID: {client.user.id})")
    print("------")

@client.tree.command(description="Add a server, opens Add Server modal.")
@app_commands.describe(
    server_name="Display name of the server",
    ip_address="IP Address players can join with.",
    port="Port number for server",
    color="Color for embed in HEX format.",
    icon_url="Icon displayed in the embed footer",
    image_url="Image displayed in the embed",
)
async def add_server(
    interaction: discord.Interaction,
    server_name: str,
    ip_address: str,
    port: int,
    color: str | None,
    icon_url: str | None,
    image_url: str | None,
):
    await client.send_embed(
        interaction, server_name, ip_address, port, color, icon_url, image_url
    )
    await interaction.response.send_message(
        f"Successfully created {server_name}!", ephemeral=True
    )

import sys

missing_envs = [e for e in ['BOT_TOKEN', 'CHANNEL_ID', 'GUILD_ID'] if not os.getenv(e)]
if missing_envs:
    print(f"Error: missing env vars {', '.join(missing_envs)}")
    sys.exit(1)

client.run(os.getenv('BOT_TOKEN'))
