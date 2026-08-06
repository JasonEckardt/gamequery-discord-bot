import json
import logging
import os
import random
import sys
import urllib
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

import a2s
import cv2
import discord
import numpy as np
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


## TODO:= Replace embed_icon with embed_thumbnail
##        embed_thumbnail will be the game logo
##        embed_icon is queried via Steam page, so we will not need this manual field
## TODO:= A mod collection link would be nice: [Mod Collection](link to mod collection)
@dataclass
class ServerConfig:
    host: str
    name: str
    port: int
    protocol: Protocol
    query_host: str
    query_port: int
    embed_color: discord.Color
    embed_id: str | None
    embed_image: str | None
    embed_thumbnail: str | None


class ServerEmbed(discord.Embed):
    def __init__(self, config: ServerConfig):
        self.update = False
        super().__init__()

        ## TODO:= Maybe we shouldn't throw away the config
        ##        and instead keep save it as self.config?
        ##        This issue crops up in _query where warn does not know embed_id

        self.add_field(name="Host", value=config.host)
        self.add_field(name="Port", value=config.port)
        self.add_field(name="Name", value=config.name)

        ## TODO:= Replace embed_icon with status icon
        ##        green => online, grey => offline, yellow/amber => not queried
        ## TODO := env for repo owner? or github url? or just keep as is?
        current_status = "notqueried"
        self.set_footer(
            icon_url=f"https://raw.githubusercontent.com/JasonEckardt/gamequery-discord-bot/refs/heads/master/assets/status_icons/{current_status}.png",
            text=f"  • {config.host}:{config.port}",
        )

        self.set_image(url=config.embed_image)

        self.timestamp = datetime.now(timezone.utc)

        if config.embed_color:
            self.color = discord.Color.from_str(config.embed_color)
        elif config.embed_image:
            req = urllib.request.Request(
                config.embed_image, headers={"User-Agent": "Mozilla/5.0"}
            )
            data = urllib.request.urlopen(req).read()
            arr = np.frombuffer(data, dtype=np.uint8)
            img = cv2.imdecode(arr, -1)
            pixels = np.float32(img.reshape(-1, 3))

            n_colors = 5
            criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 200, 0.1)
            flags = cv2.KMEANS_RANDOM_CENTERS

            _, _, pallete = cv2.kmeans(pixels, n_colors, None, criteria, 10, flags)

            def is_neutral(color):
                b, g, r = color
                saturation = max(r, g, b) - min(r, g, b)
                brightness = (int(r) + int(g) + int(b)) / 3
                return saturation < 30 or brightness > 200

            vibrant = [c for c in pallete if not is_neutral(c)]
            dominant = vibrant[0] if vibrant else pallete[0]

            BRIGHT_FACTOR = 1.5
            self.color = discord.Color.from_rgb(
                min(255, int(dominant[2] * BRIGHT_FACTOR)),
                min(255, int(dominant[1] * BRIGHT_FACTOR)),
                min(255, int(dominant[0] * BRIGHT_FACTOR)),
            )
        else:
            colors = [
                discord.Color.brand_red(),
                discord.Color.brand_green(),
                discord.Color.og_blurple(),
                discord.Color.blurple(),
                discord.Color.greyple(),
                discord.Color.fuchsia(),
                discord.Color.yellow(),
                discord.Color.dark_blue(),
                discord.Color.dark_green(),
                discord.Color.dark_red(),
                discord.Color.dark_grey(),
                discord.Color.light_grey(),
                discord.Color.dark_magenta(),
                discord.Color.dark_gold(),
                discord.Color.dark_orange(),
                discord.Color.dark_teal(),
                discord.Color.teal(),
                discord.Color.blue(),
                discord.Color.green(),
                discord.Color.purple(),
                discord.Color.magenta(),
                discord.Color.gold(),
                discord.Color.orange(),
                discord.Color.red(),
            ]
            self.color = random.choice(colors)

    @classmethod
    async def build(cls, config: ServerConfig):
        self = cls(config)
        res = await self._query(config.query_host, config.query_port, config.protocol)
        self.update = res
        if self.title is None or self.update:
            self.title = config.name
        return self

    ## TODO := Fail Query X times => Mark as offline, on next reconnect => Mark Online
    async def _query(self, address: str, port: int, protocol: Protocol) -> bool:
        """
        -> True: Rebuild embed
        -> False: Don't rebuild embed
        """
        if protocol == Protocol.NONE:
            return False
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
                logger.warning(
                    f"a2s: Failed to query {address}:{port}, waiting X more times before marking offline: {e}"
                )
                return False

            self.timestamp = datetime.now(timezone.utc)
            self.title = info.game
            self.add_field(
                name="Players",
                value=f"{info.player_count!s}/{info.max_players!s}",
            )
            self.add_field(name="Game Version", value=info.version)
            if info.game == "Abiotic Factor":
                self.add_field(name="Story Progress", value=rules["StoryProgress_s"])
            ## TODO:= Parse rules['mods'] and display it nicer, either bullet newline or seperated
            if info.game == "Project Zomboid":
                self.add_field(name="Mod Count", value=rules["modCount"])
                self.add_field(name="Mods", inline=False, value=rules["mods"])
            logger.debug(
                f"{address}:{port} ok: {info.game}, {info.player_count!s}/{info.max_players!s}"
            )
            return True
        else:
            logger.warning("The protocol for host {address} is unknown")
        return False


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
            logger.error(f"Cannot update {config.name}, missing embed_id")
            return
        self.servers[str(config.embed_id)] = {
            "host": config.host,
            "name": config.name,
            "port": config.port,
            "query_host": config.query_host,
            "query_port": config.query_port,
            "protocol": config.protocol.value,
            "embed_color": config.embed_color,
            "embed_id": config.embed_id,
            "embed_image": config.embed_image,
            "embed_thumbnail": config.embed_thumbnail,
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

    @tasks.loop(seconds=int(os.getenv("PING_INTERVAL", "60")))
    async def query_loop(self):
        for embed_id, attrs in list(server_store.servers.items()):
            try:
                config = ServerConfig(
                    host=attrs["host"],
                    name=attrs["name"],
                    port=attrs["port"],
                    protocol=Protocol(attrs["protocol"]),
                    query_host=attrs["query_host"],
                    query_port=attrs["query_port"],
                    embed_color=attrs["embed_color"],
                    embed_id=attrs["embed_id"],
                    embed_image=attrs["embed_image"],
                    embed_thumbnails=attrs["embed_thumbnails"],
                )
                embed = await ServerEmbed.build(config)
                if embed.update:
                    try:
                        message = await self.channel.fetch_message(
                            int(attrs["embed_id"])
                        )
                        await message.edit(embed=embed)
                    except discord.NotFound:
                        server_store.delete(embed_id)
                        message = await self.channel.send(embed=embed)
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
    query_port="Port used for game query",
    embed_color="Hex embed color",
    embed_image="URL to embed vertical grid banner",
    embed_thumbnail="URL to game logo",
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
    embed_image: str | None,
    embed_thumbnail: str | None,
):
    new_server = ServerConfig(
        host=host,
        name=name,
        port=port,
        protocol=protocol,
        query_host=query_host,
        query_port=query_port,
        embed_color=embed_color,
        embed_id=None,
        embed_image=embed_image,
        embed_thumbnail=embed_thumbnail,
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
