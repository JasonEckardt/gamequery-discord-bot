import json
import logging
import os
import random
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import ClassVar
from urllib import error, parse, request

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

MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))

discord.utils.setup_logging(
    level=os.getenv("LOG_LEVEL", "INFO"),
    root=True,
)

logger = logging.getLogger(__name__)
logging.getLogger("discord.client").setLevel(logging.ERROR)


class Protocol(Enum):
    A2S = "A2S"
    MINECRAFT = "Minecraft"
    NONE = "None"


class ServerStatus(Enum):
    OFFLINE = "Offline"
    ONLINE = "Online"
    PENDING = "Pending"
    UNQUERIED = "Unqueried"


## optional todo:= A mod collection link would be nice: [Mod Collection](link to mod collection)
@dataclass
class ServerConfig:
    host: str
    name: str
    port: int
    protocol: Protocol
    query_host: str | None
    query_port: int | None
    embed_color: discord.Color
    embed_id: str | None
    embed_image: str | None
    embed_thumbnail: str | None


class ServerEmbed(discord.Embed):
    _RANDOM_EMBED_COLORS: ClassVar[list[discord.Color]] = [
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

    def __init__(self, config: ServerConfig, tries: int = 0):
        self.status = ServerStatus.PENDING
        self.tries = tries
        self.update = False
        super().__init__()

        self.add_field(name="Host", value=config.host)
        self.add_field(name="Port", value=config.port)
        self.add_field(name="Name", value=config.name)

        self.set_image(url=config.embed_image)
        self.set_thumbnail(url=config.embed_thumbnail)

        self.timestamp = datetime.now(timezone.utc)

        request_img = None
        if config.embed_color:
            self.color = discord.Color.from_str(config.embed_color)
        elif config.embed_image or config.embed_thumbnail:
            request_img = config.embed_image or config.embed_thumbnail

        if request_img is not None:
            try:
                req = request.Request(
                    request_img, headers={"User-Agent": "Mozilla/5.0"}
                )
                data = request.urlopen(req, timeout=10).read()
                arr = np.frombuffer(data, dtype=np.uint8)
                img = cv2.imdecode(arr, -1)
                if img is None:
                    raise ValueError(
                        f"Could not decode image data from '{request_img}'"
                    )
                pixels = np.float32(img.reshape(-1, 3))

                n_colors = 5
                criteria = (
                    cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
                    200,
                    0.1,
                )
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
            except (error.URLError, OSError, ValueError, cv2.error) as e:
                logger.warning(
                    f"Failed to derive embed color from '{request_img}': {e}"
                )
                self.color = random.choice(self._RANDOM_EMBED_COLORS)
        elif not config.embed_color:
            self.color = random.choice(self._RANDOM_EMBED_COLORS)

    @classmethod
    async def build(
        cls,
        config: ServerConfig,
        tries: int = 0,
        previous_status: ServerStatus | None = None,
    ) -> discord.Embed:
        self = cls(config, tries)
        if not config.embed_color:
            config.embed_color = self.color
            if config.embed_id is not None:
                server_store.update(config)

        await self._query(
            config.query_host, config.query_port, config.protocol, config.name
        )
        self.update = self.status != previous_status
        if self.title is None and self.update:
            self.title = config.name

        if self.status != ServerStatus.UNQUERIED:
            icon_url = f"https://raw.githubusercontent.com/JasonEckardt/gamequery-discord-bot/refs/heads/0.2.0/assets/{self.status.value}.png"
            footer_text = f"{self.status.value}  •  {config.host}:{config.port}"
        else:
            icon_url = None
            footer_text = f"{config.host}:{config.port}"

        self.set_footer(icon_url=icon_url, text=footer_text)

        return self

    async def _query(
        self, address: str, port: int, protocol: Protocol, name: str
    ) -> None:
        if protocol == Protocol.NONE:
            self.status = ServerStatus.UNQUERIED
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
                if self.tries >= MAX_RETRIES:
                    logger.debug(f"a2s: {name} - {address}:{port} still offline")
                    self.status = ServerStatus.OFFLINE
                    return

                self.tries += 1
                if self.tries >= MAX_RETRIES:
                    logger.warning(
                        f"a2s: {name} - {address}:{port} marked offline after {MAX_RETRIES} failed attempts"
                    )
                    self.status = ServerStatus.OFFLINE
                else:
                    logger.warning(
                        f"a2s: {name} - {address}:{port} failed query, waiting {MAX_RETRIES - self.tries} more times before marking offline: {e}"
                    )
                    self.status = ServerStatus.PENDING
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
            ## TODO:= Parse rules['mods'] and display it nicer, either bullet newline or seperated
            if info.game == "Project Zomboid":
                self.add_field(name="Mod Count", value=rules["modCount"])
                self.add_field(name="Mods", inline=False, value=rules["mods"])
            logger.debug(
                f"{address}:{port} ok: {info.game}, {info.player_count!s}/{info.max_players!s}"
            )
            self.status = ServerStatus.ONLINE
            self.tries = 0
        else:
            logger.warning("The protocol for host {address} is unknown")
            self.status = ServerStatus.UNQUERIED


class ServerStore:
    def __init__(self):
        self.servers = {}
        try:
            with open(OUT_SERVER_DATA, "r") as f:
                self.servers = json.load(f)
                logger.info("Loaded Server Store")
                logger.debug(
                    f"Loaded Server Store:\n {json.dumps(self.servers, indent=2)}"
                )
        except FileNotFoundError:
            logger.info("Initialized new server data store")

    def _apply(self):
        with open(OUT_TMP, "w") as f:
            json.dump(self.servers, f, indent=2)
        os.replace(OUT_TMP, OUT_SERVER_DATA)
        logger.debug(f"Updated server_store:\n {json.dumps(self.servers, indent=2)}")

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
            "protocol": config.protocol.value,
            "query_host": config.query_host,
            "query_port": config.query_port,
            "embed_color": config.embed_color,
            "embed_id": config.embed_id,
            "embed_image": config.embed_image,
            "embed_thumbnail": config.embed_thumbnail,
        }
        self._apply()


def _text_field(text: str, description: str | None = None, required: bool = True):
    return discord.ui.Label(
        text=text,
        description=description,
        component=discord.ui.TextInput(
            style=discord.TextStyle.short, max_length=128, required=required
        ),
    )


async def _sanitize_embed_color(
    interaction: discord.Interaction, embed_color: str | None
) -> str | None:
    if not embed_color:
        return None
    embed_color = embed_color.strip()
    if not embed_color.startswith(("#", "0x")) and not embed_color.startswith("rgb("):
        embed_color = f"#{embed_color}"
    try:
        discord.Color.from_str(embed_color)
    except ValueError:
        await interaction.followup.send(
            f"'{embed_color}' is not a valid embed color, so one was picked "
            "automatically. Edit the server again to set a custom color.",
            ephemeral=True,
        )
        return None
    return embed_color


def _sanitize_embed_url(url: str | None) -> str | None:
    if not url:
        return None
    url = url.strip()
    parsed = parse.urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(
            f"'{url}' is not a valid URL. It must start with http:// or https://."
        )
    return url


def _parse_server_embed(embed: discord.Embed) -> ServerConfig | None:
    fields = {f.name: f.value for f in embed.fields}
    host, port_raw, name = fields.get("Host"), fields.get("Port"), fields.get("Name")
    if not host or not port_raw or not name:
        return None
    try:
        port = int(port_raw)
    except (TypeError, ValueError):
        return None

    return ServerConfig(
        host=host,
        name=name,
        port=port,
        protocol=Protocol.NONE,
        query_host=None,
        query_port=None,
        embed_color=str(embed.color) if embed.color else None,
        embed_id=None,
        embed_image=embed.image.url if embed.image else None,
        embed_thumbnail=embed.thumbnail.url if embed.thumbnail else None,
    )


class EditConnectionModal(discord.ui.Modal, title="Edit Connection Details"):
    host = _text_field("Host Address")
    port = _text_field("Host Port")
    protocol = discord.ui.Label(
        text="Protocol",
        component=discord.ui.Select(
            options=[
                discord.SelectOption(label=p.name, value=p.value) for p in Protocol
            ],
            required=True,
        ),
    )
    query_host = _text_field("Query Address")
    query_port = _text_field("Query Port")

    def __init__(self, store: ServerStore, message: discord.Message):
        super().__init__()
        self.store = store
        self.message = message

        this_server = store.servers.get(str(message.id))
        if this_server is None:
            raise ValueError(f"No stored server config found for message {message.id}")
        self.this_server = this_server

        for field_name in ("host", "port", "query_host", "query_port"):
            label: discord.ui.Label = getattr(self, field_name)
            label.component.default = str(this_server[field_name])

        current_protocol = this_server["protocol"]
        for option in self.protocol.component.options:
            option.default = option.value == current_protocol

    async def on_submit(self, interaction: discord.Interaction, /) -> None:
        await interaction.response.defer(ephemeral=True)

        try:
            port = int(self.port.component.value)
            query_port = int(self.query_port.component.value)
        except ValueError:
            await interaction.followup.send(
                "Host Port and Query Port must both be whole numbers.",
                ephemeral=True,
            )
            return

        protocol = Protocol(self.protocol.component.values[0])

        updated = ServerConfig(
            host=self.host.component.value,
            name=self.this_server["name"],
            port=port,
            protocol=protocol,
            query_host=self.query_host.component.value,
            query_port=query_port,
            embed_color=self.this_server["embed_color"],
            embed_id=self.message.id,
            embed_image=self.this_server["embed_image"],
            embed_thumbnail=self.this_server["embed_thumbnail"],
        )

        self.store.update(updated)

        embed = await ServerEmbed.build(updated)
        await self.message.edit(embed=embed)

        await interaction.followup.send(
            f"Updated connection details for {updated.name}.", ephemeral=True
        )


class EditDisplayModal(discord.ui.Modal, title="Edit Display Details"):
    name = _text_field("Server Name")
    embed_color = _text_field("Embed Color", required=False)
    embed_image = _text_field("Embed Image / Banner Image", required=False)
    embed_thumbnail = _text_field("Embed Thumbnail / Game Logo", required=False)

    def __init__(self, store: ServerStore, message: discord.Message):
        super().__init__()
        self.store = store
        self.message = message

        this_server = store.servers.get(str(message.id))
        if this_server is None:
            raise ValueError(f"No stored server config found for message {message.id}")
        self.this_server = this_server

        for field_name in ("name", "embed_color", "embed_image", "embed_thumbnail"):
            label: discord.ui.Label = getattr(self, field_name)
            value = this_server[field_name]
            label.component.default = str(value) if value else ""

    async def on_submit(self, interaction: discord.Interaction, /) -> None:
        await interaction.response.defer(ephemeral=True)

        embed_color = await _sanitize_embed_color(
            interaction, self.embed_color.component.value
        )

        try:
            embed_image = _sanitize_embed_url(self.embed_image.component.value)
            embed_thumbnail = _sanitize_embed_url(self.embed_thumbnail.component.value)
        except ValueError as e:
            await interaction.followup.send(str(e), ephemeral=True)
            return

        updated = ServerConfig(
            host=self.this_server["host"],
            name=self.name.component.value,
            port=self.this_server["port"],
            protocol=Protocol(self.this_server["protocol"]),
            query_host=self.this_server["query_host"],
            query_port=self.this_server["query_port"],
            embed_color=embed_color,
            embed_id=self.message.id,
            embed_image=embed_image,
            embed_thumbnail=embed_thumbnail,
        )

        self.store.update(updated)

        embed = await ServerEmbed.build(updated)
        await self.message.edit(embed=embed)

        await interaction.followup.send(
            f"Updated display details for {updated.name}.", ephemeral=True
        )


class DeleteServerModal(discord.ui.Modal, title="Delete Game Server"):
    name = _text_field("Type server name to confirm delete")

    def __init__(self, store: ServerStore, message: discord.Message):
        super().__init__()
        self.store = store
        self.message = message

        this_server = store.servers.get(str(message.id))
        if this_server is None:
            raise ValueError(f"No stored server config found for message {message.id}")
        self.this_server = this_server

        self.name.component.placeholder = self.this_server["name"]

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        entered_name = self.name.component.value
        expected_name = self.this_server["name"]
        if entered_name != expected_name:
            await interaction.followup.send(
                f"'{entered_name}' does not match server name '{expected_name}'. "
                "Deletion cancelled.",
                ephemeral=True,
            )
            return

        self.store.delete(str(self.message.id))
        try:
            await self.message.delete()
        except discord.NotFound:
            pass

        await interaction.followup.send(f"Deleted {expected_name}.", ephemeral=True)


class AddServerFromEmbedModal(discord.ui.Modal, title="Add to Server Store"):
    protocol = discord.ui.Label(
        text="Protocol",
        component=discord.ui.Select(
            options=[
                discord.SelectOption(label=p.name, value=p.value) for p in Protocol
            ],
            required=True,
        ),
    )
    query_host = _text_field("Query Address", required=False)
    query_port = _text_field("Query Port", required=False)

    def __init__(
        self, store: ServerStore, message: discord.Message, parsed: ServerConfig
    ):
        super().__init__()
        self.store = store
        self.message = message
        self.parsed = parsed

        for option in self.protocol.component.options:
            option.default = option.value == Protocol.NONE.value

    async def on_submit(self, interaction: discord.Interaction, /) -> None:
        await interaction.response.defer(ephemeral=True)

        protocol = Protocol(self.protocol.component.values[0])
        query_host = self.query_host.component.value or None
        query_port_raw = self.query_port.component.value

        query_port = None
        if protocol != Protocol.NONE:
            if not query_host or not query_port_raw:
                await interaction.followup.send(
                    "'Query Address' and 'Query Port' are required unless "
                    "Protocol is 'None'.",
                    ephemeral=True,
                )
                return
            try:
                query_port = int(query_port_raw)
            except ValueError:
                await interaction.followup.send(
                    "Query Port must be a whole number.", ephemeral=True
                )
                return

        new_server = ServerConfig(
            host=self.parsed.host,
            name=self.parsed.name,
            port=self.parsed.port,
            protocol=protocol,
            query_host=query_host,
            query_port=query_port,
            embed_color=self.parsed.embed_color,
            embed_id=self.message.id,
            embed_image=self.parsed.embed_image,
            embed_thumbnail=self.parsed.embed_thumbnail,
        )
        self.store.update(new_server)

        embed = await ServerEmbed.build(new_server)
        await self.message.edit(embed=embed)

        await interaction.followup.send(
            f"Added {new_server.name} to the server store.", ephemeral=True
        )


class Client(discord.Client):
    user: discord.ClientUser

    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.tree.on_error = self.on_tree_error
        # In-memory only, keyed by embed_id: (tries, last-seen status). Never
        # persisted to server_store — it's poll-loop runtime state, not config.
        self._poll_state: dict[str, tuple[int, ServerStatus | None]] = {}

    async def on_tree_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ):
        logger.error(
            f"Unhandled error in command '{interaction.command.name if interaction.command else '?'}': {error}",
            exc_info=error,
        )
        message = "Something went wrong running that command."
        try:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        except discord.HTTPException:
            pass

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
                    embed_thumbnail=attrs["embed_thumbnail"],
                )
                tries, previous_status = self._poll_state.get(embed_id, (0, None))
                embed = await ServerEmbed.build(
                    config, tries=tries, previous_status=previous_status
                )
                self._poll_state[embed_id] = (embed.tries, embed.status)
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
                        self._poll_state[str(message.id)] = self._poll_state.pop(
                            embed_id
                        )
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
@app_commands.default_permissions(administrator=True)
@app_commands.describe(
    name="Display name",
    host="Server IP or hostname",
    port="Connection port",
    protocol="Query protocol",
    query_host="Host used for game query (required unless protocol is None)",
    query_port="Port used for game query (required unless protocol is None)",
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
    query_host: str | None,
    query_port: int | None,
    embed_color: str | None,
    embed_image: str | None,
    embed_thumbnail: str | None,
):
    await interaction.response.defer(ephemeral=True)

    if protocol != Protocol.NONE and (query_host is None or query_port is None):
        await interaction.followup.send(
            "'query_host' and 'query_port' are required unless 'protocol' is 'None'.",
            ephemeral=True,
        )
        return

    embed_color = await _sanitize_embed_color(interaction, embed_color)

    try:
        embed_image = _sanitize_embed_url(embed_image)
        embed_thumbnail = _sanitize_embed_url(embed_thumbnail)
    except ValueError as e:
        await interaction.followup.send(str(e), ephemeral=True)
        return

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

    await interaction.followup.send(
        f"Successfully created {new_server.name}!", ephemeral=True
    )


_NOT_A_SERVER_EMBED = (
    "That message isn't a tracked server embed. "
    "Right-click the server's status embed message instead."
)


## TODO:= Replace with matching permissions: Manage Messages, Delete Messages, etc.
@client.tree.context_menu(name="Edit Connection Details")
@app_commands.default_permissions(administrator=True)
async def edit_server_connection(
    interaction: discord.Interaction, message: discord.Message
):
    if str(message.id) not in server_store.servers:
        await interaction.response.send_message(_NOT_A_SERVER_EMBED, ephemeral=True)
        return
    await interaction.response.send_modal(EditConnectionModal(server_store, message))


@client.tree.context_menu(name="Edit Display Details")
@app_commands.default_permissions(administrator=True)
async def edit_server_display(
    interaction: discord.Interaction, message: discord.Message
):
    if str(message.id) not in server_store.servers:
        await interaction.response.send_message(_NOT_A_SERVER_EMBED, ephemeral=True)
        return
    await interaction.response.send_modal(EditDisplayModal(server_store, message))


@client.tree.context_menu(name="Delete Game Server")
@app_commands.default_permissions(administrator=True)
async def delete_game_server(
    interaction: discord.Interaction, message: discord.Message
):
    if str(message.id) not in server_store.servers:
        await interaction.response.send_message(_NOT_A_SERVER_EMBED, ephemeral=True)
        return
    await interaction.response.send_modal(DeleteServerModal(server_store, message))


@client.tree.context_menu(name="Add to Server Store")
@app_commands.default_permissions(administrator=True)
async def add_to_server_store(
    interaction: discord.Interaction, message: discord.Message
):
    if str(message.id) in server_store.servers:
        await interaction.response.send_message(
            "This message is already a tracked server.", ephemeral=True
        )
        return

    if not message.embeds:
        await interaction.response.send_message(_NOT_A_SERVER_EMBED, ephemeral=True)
        return

    parsed = _parse_server_embed(message.embeds[0])
    if parsed is None:
        await interaction.response.send_message(
            "That embed doesn't look like a server config — it needs Host, "
            "Port, and Name fields, with Port as a whole number.",
            ephemeral=True,
        )
        return

    await interaction.response.send_modal(
        AddServerFromEmbedModal(server_store, message, parsed)
    )


if __name__ == "__main__":
    server_store = ServerStore()

    missing_envs = [
        e for e in ["BOT_TOKEN", "CHANNEL_ID", "GUILD_ID"] if not os.getenv(e)
    ]
    if missing_envs:
        logger.error(f"Error: missing env vars {', '.join(missing_envs)}")
        sys.exit(1)

    client.run(os.getenv("BOT_TOKEN"), log_handler=None)
