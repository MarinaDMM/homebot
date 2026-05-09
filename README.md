# homebot

A personal assistant Telegram bot for your Mac. Reminders, weather, trash schedule, email→calendar, and HomeKit control over Telegram. Single-tenant, runs locally, no cloud dependencies (except Telegram + Google APIs).

## What it does

- **Reminders** in chat. `/remind every Tuesday 19:00 take out trash`. Recurring or one-off, parsed from natural-ish English.
- **Morning briefing** at the time of your choice: weather, KNMI severe-weather alerts, today's calendar events, trash if pickup is today/tomorrow.
- **Email → Calendar.** Polls Gmail every 30 min, uses Claude to spot real events (flights, doctor appointments, restaurants), DMs you with **Add** / **Skip** buttons.
- **HomeKit control** through Apple Shortcuts. `/lights on`, `/scene movie`, `/lock front_door` (with a confirmation step on locks).
- **Dutch trash schedule** via mijnafvalwijzer.nl, geocoding via PDOK Locatieserver. Postcode/house number set from chat (`/setlocation`).

## Architecture

```
Telegram ↔ python-telegram-bot ↔ APScheduler ↔ {SQLite, Gmail API, Calendar API, Buienradar, mijnafvalwijzer, KNMI, /usr/bin/shortcuts}
```

Single Python process, persisted state in SQLite, kept alive by a launchd LaunchAgent. HomeKit is reached via the macOS `shortcuts` CLI — no Homebridge or Home Assistant required.

## Requirements

- macOS (any recent version with the `shortcuts` CLI — Monterey or later)
- Python 3.10+
- A Telegram bot (token from `@BotFather`)
- A Google Cloud project with Gmail + Calendar APIs enabled (5-min setup, see below)
- *(Optional)* an Anthropic API key for email→calendar
- *(Optional)* HomeKit accessories you want to control via Shortcuts

## Quick start

```sh
git clone https://github.com/YOUR_USERNAME/homebot.git ~/homebot
cd ~/homebot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml
# Edit config.yaml: bot_token + authorized_user_id at minimum
python bot.py
```

Then in Telegram, find your bot, send `/start`, and follow the prompts.

## Setup details

### 1. Telegram

- **Bot token**: message [@BotFather](https://t.me/BotFather) → `/newbot` → follow prompts.
- **Your user ID**: message [@userinfobot](https://t.me/userinfobot), it replies with your numeric ID.

Both go in `config.yaml` under `telegram:`.

### 2. Google OAuth (Gmail + Calendar)

1. Create a project: https://console.cloud.google.com/projectcreate
2. Enable Gmail API + Calendar API in that project.
3. Configure OAuth consent screen → External → add yourself as a test user.
4. Credentials → Create OAuth client → **Desktop app** → download JSON → save as `google_credentials.json` in the project folder.

First time you run the bot, a browser opens for you to consent. Token caches to `google_token.json`. After that it's silent.

### 3. Anthropic API (optional, for email→calendar)

Add your key to `config.yaml` under `llm.anthropic_api_key`. Leave blank to disable email scanning.

### 4. HomeKit (optional)

See [shortcuts-to-create.md](shortcuts-to-create.md). Make Shortcuts in the Shortcuts app named the same as the entries in `config.yaml > homekit`. The bot calls `shortcuts run "<name>"` to fire them.

### 5. Auto-start on login

```sh
sed -i '' "s|YOUR_USERNAME|$(whoami)|g; s|YOUR_PROJECT_DIR|$HOME/homebot|g" launchagent/com.user.homebot.plist
cp launchagent/com.user.homebot.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.user.homebot.plist
launchctl start com.user.homebot
```

Restart after config edits:
```sh
launchctl kickstart -k gui/$(id -u)/com.user.homebot
```

## Commands

| Command | Example |
|---|---|
| `/setlocation <pc> <hnr>` | `/setlocation 1011AB 42` (NL) |
| `/location` | Show current address |
| `/remind <when> <text>` | `/remind every Tuesday 19:00 take out trash` |
| `/list` / `/delete <id>` | Manage reminders |
| `/lights on\|off` | Toggle lights |
| `/scene <name>` | Run a HomeKit scene |
| `/lock <name>` / `/unlock <name>` | With confirmation buttons |
| `/shortcuts` | List installed Shortcuts |
| `/weather` | Now + today + KNMI alerts |
| `/trash` | Upcoming pickups |
| `/today` | Today's calendar |
| `/briefing` | Full briefing now |

### Reminder formats accepted

- `every Tuesday at 19:00 take out trash`
- `every weekday 9am standup`
- `every Mon, Wed, Fri 7am gym`
- `tomorrow 14:30 dentist`
- `today 22:00 take vitamins`
- `in 2 hours water plants`
- `on 2026-05-15 16:00 pick up package`

## Localization notes

The trash and weather integrations are Netherlands-specific (mijnafvalwijzer.nl, Buienradar, KNMI). If you're elsewhere:

- **Trash**: replace `integrations/trash.py` with your municipality's API.
- **Weather**: replace `integrations/weather.py` with OpenWeatherMap, NWS, etc.
- **Geocoding**: `integrations/geocode.py` uses PDOK (NL only); swap for Nominatim or Google's Geocoding API for global support.

PRs welcome.

## Project layout

```
homebot/
├── bot.py                  # Telegram handlers, scheduler bootstrap
├── parsing.py              # Natural-language reminder parser
├── storage.py              # SQLite (reminders, settings, processed emails)
├── config.example.yaml     # Template — copy to config.yaml
├── requirements.txt
├── integrations/
│   ├── geocode.py          # PDOK Locatieserver
│   ├── homekit.py          # macOS `shortcuts` CLI wrapper
│   ├── weather.py          # Buienradar
│   ├── trash.py            # mijnafvalwijzer
│   ├── alerts.py           # KNMI severe-weather warnings
│   ├── google_auth.py      # OAuth bootstrap
│   ├── gmail_client.py     # Read/parse messages
│   ├── calendar_client.py  # List today / insert events
│   └── event_extractor.py  # Claude prompt for event detection
├── launchagent/
│   └── com.user.homebot.plist
└── shortcuts-to-create.md  # HomeKit Shortcuts to set up
```

## Troubleshooting

- **Shortcuts permission denied**: System Settings → Privacy & Security → Automation → enable Shortcuts for Terminal/your shell.
- **Gmail OAuth keeps re-prompting**: delete `google_token.json`, re-run.
- **`zsh: killed`**: usually a Python version issue (need 3.10+) or quarantined binary. `xattr -dr com.apple.quarantine /path/to/python` fixes the latter.
- **Bot silent**: tail `bot.log` and `launchd.err.log`.

## Security notes

- `config.yaml` and `google_*.json` are in `.gitignore` — never commit them.
- The bot only responds to your `authorized_user_id`. Anyone else who finds it gets "Not authorized."
- Locks default to `require_confirmation: true`. Don't disable unless you know what you're doing.
- Telegram bot tokens are credentials — rotate via `/revoke` to BotFather if leaked.

## License

[MIT](LICENSE)

## Contributing

PRs welcome — especially additional country/region integrations, new reminder formats, or HomeKit accessory wrappers. Keep individual integrations isolated in `integrations/` so swap-in alternatives stay clean.
