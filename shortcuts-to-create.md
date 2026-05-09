# Shortcuts to create in the Shortcuts app

The bot triggers HomeKit by running named Shortcuts. Open the **Shortcuts** app on your Mac and create these.

## Lights

| Shortcut name | What it does |
|---|---|
| `Lights On`   | Turns on your "main" lights or runs your default daytime scene |
| `Lights Off`  | Turns off all lights (or runs your "All Off" scene) |
| `Movie Night` | Runs the Movie Night HomeKit scene |
| `Bedtime`     | Runs the Bedtime scene |

## Locks

| Shortcut name        | What it does |
|---|---|
| `Lock Front Door`    | Locks the front door |
| `Unlock Front Door`  | Unlocks the front door |

## Sanity check

```sh
shortcuts list | grep -E 'Lights|Movie|Bedtime|Lock'
```

Test one:

```sh
shortcuts run "Lights On"
```

If macOS prompts for permission the first time, allow it.
