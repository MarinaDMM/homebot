# Shortcuts to create in the Shortcuts app

The bot triggers HomeKit by running named Shortcuts. Open the **Shortcuts** app on your Mac and create these (each as a new shortcut). All you need inside each one is a *Control Home* action set to do the right thing — Shortcuts will read your existing Apple Home setup automatically.

> Tip: in Shortcuts, click `+`, search "Control Home", pick the accessory or scene, configure the state, save, and rename to match the names below.

## Lights

| Shortcut name | What it does |
|---|---|
| `Lights On`   | Turns on your "main" lights or runs your default daytime scene |
| `Lights Off`  | Turns off all lights (or runs your "All Off" scene) |
| `Movie Night` | Runs the Movie Night HomeKit scene (dim, warm) |
| `Bedtime`     | Runs the Bedtime scene (off / nightlights) |

## Locks

| Shortcut name        | What it does |
|---|---|
| `Lock Front Door`    | Locks the front door |
| `Unlock Front Door`  | Unlocks the front door |

## Sanity check

After creating these, run from the terminal:

```sh
shortcuts list | grep -E 'Lights|Movie|Bedtime|Lock'
```

You should see all six.

Test one:

```sh
shortcuts run "Lights On"
```

If macOS prompts for permission the first time, allow it. Once approved, the bot will be able to run any of these silently.

## Adding more

To add scenes to the bot, create the shortcut, then add it under `homekit.lights.scenes` in `config.yaml`:

```yaml
homekit:
  lights:
    scenes:
      movie: "Movie Night"
      bedtime: "Bedtime"
      reading: "Reading Mode"   # ← new
```

To add another lock, add a new key under `homekit.locks`:

```yaml
homekit:
  locks:
    front_door:
      lock: "Lock Front Door"
      unlock: "Unlock Front Door"
      require_confirmation: true
    back_door:                  # ← new
      lock: "Lock Back Door"
      unlock: "Unlock Back Door"
      require_confirmation: true
```

Restart the bot after editing config (`launchctl kickstart -k gui/$(id -u)/com.mari.bot`).
