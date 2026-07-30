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
        super().__init__(color=config.color, **kwargs)
        self.set_thumbnail(url=config.embed_icon)
        self.set_image(url=config.embed_image)

        if config.protocol == Protocol.A2S:
            query = (config.query_host, config.query_port)
            info = a2s.info(query)
            rules = a2s.rules(query)
            self.title = info.game
            self.add_field(name="Name", value=config.name) # User enter server name
            self.add_field(name="Players", value=f"{str(info.player_count)}/{str(info.max_players)}")
            self.add_field(name="Game Version", value=info.version)
            if config.game = "Abiotic Factor":
                self.add_field(name="Hardcore", value=rules["Hardcore_b"]
                self.add_field(name="Story Progress", value=rules["StoryProgress_s"]
            if config.game = "Project Zomboid":
                self.add_field(name"Mod Count", value=rules["mod_count"]
                self.add_field(name="Mods", value=rules["mods"]

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
    async def on_ready(self):
        print(self.user, "is ready!")

intents = discord.Intents.default()
intents.message_content = True
client = Client(intents=intents)
#client.run(os.getenv('BOT_TOKEN'))

servers = ServerStore()
new_server = ServerConfig("lngs.lambdastack.org", "Abiotic Gamer", 7777, Protocol.A2S, "10.0.3.103", 27015, "#FFFFFF","someiconlol", "some_msg_id_lol", "someimglol")
servers.update(new_server)
query = (new_server.query_host, new_server.query_port)
server_players = a2s.players(query)
server_info = a2s.info(query)
server_rules = a2s.rules(query)

print(server_info, server_rules, server_players)
