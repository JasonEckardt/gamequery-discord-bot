# Game Query Discord Bot

## Installation

### `env` variables

### `systemd`

Deploy the repo to `/opt/game_query_discord_bot` (with its `.venv` and `.env` in place), then save the unit below to `/etc/systemd/system/game_query_discord_bot.service`:

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
