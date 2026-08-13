# Game Query Discord Bot

## Installation

```sh
cd /opt
git clone https://github.com/JasonEckardt/gamequery-discord-bot.git
mv gamequery-discord-bot game_query_discord_bot
```

### `env` variables

### `systemd`

Deploy the repo to `/opt/game_query_discord_bot` (with its `.venv` and `.env` in place), then create the service account the unit runs as and give it ownership of the deploy directory (the bot writes `server_data.json` to its working directory):

```sh
sudo useradd --system --no-create-home --shell /usr/sbin/nologin game_query_discord_bot
sudo chown -R game_query_discord_bot: /opt/game_query_discord_bot
```

Save the unit below to `/etc/systemd/system/game_query_discord_bot.service`:

```
[Unit]
Description=Python Discord Bot Game Query Server
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=/opt/game_query_discord_bot
ExecStart=/opt/game_query_discord_bot/.venv/bin/python3 main.py
Restart=on-failure
User=game_query_discord_bot

[Install]
WantedBy=multi-user.target
```

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now game_query_discord_bot
```

## Operations

### Add a server

### Edit a server

### Delete a server
