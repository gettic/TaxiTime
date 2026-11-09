# Taxi Time

A World of Warcraft addon for **WoW Forever** that learns how long each flight path takes. On your first flight of a route it records the time. On later flights it shows a bar that fills up as you fly, with a small gryphon (Alliance) or wind rider (Horde) flapping along the top and the time left.

At a flight master it also shows each destination's time in the map tooltip, and it counts the gold and time you spend on flights.

Version 0.1.0. Please report any problems you find.

- [Install](#install)
- [How it works](#how-it-works)
- [Flight-map tooltips](#flight-map-tooltips)
- [Flight totals](#flight-totals)
- [Starter times and export](#starter-times-and-export)
- [Slash commands](#slash-commands)
- [Chat messages](#chat-messages)
- [Known limits](#known-limits)
- [Art](#art)
- [For developers](#for-developers)

## Install

1. Download the zip from the latest release.
2. Unzip the `TaxiTime` folder into your game's `Interface\AddOns\` folder, so you have `Interface\AddOns\TaxiTime\TaxiTime_Forever.toc`.
3. Fully restart the game (not just `/reload`). The game only finds new picture files after a full restart. Do this after each update too.

## How it works

| Flight | What you see |
|---|---|
| First flight of a route | An orange, pulsing "Recording" bar that counts up. When you land, it turns green and shows the saved time. |
| Later flights | A blue bar that fills over the saved time, with the flyer moving along the top, a cloud drifting by and the time left ("1:12 / 2:05"). |
| Longer than the saved time | The bar stays full and shows the extra time, like "+0:04". |
| Landing | When the time is saved, a small sparkle where the flyer lands. Then the bar fades out. |

The saved times are shared by all your characters on the account.

### Times correct themselves

Every clean flight saves its time as the route's new time, so a route's time stays up to date. If a new time is much shorter than the saved one (less than 80% of it), it only counts when you land at the destination. Then the chat says `Updated A > B: old -> new`.

### Flights that are not recorded

- You logged out, logged in, disconnected or used `/reload` during the flight. The bar still shows after you are back, but the time is not saved, because it would include the time you were away.
- The flight landed during a loading screen.
- You asked for an early landing.
- The flight was shorter than 5 seconds.
- On a new route: you didn't land near the destination.

## Flight-map tooltips

At a flight master, point at a destination on the map. The tooltip shows `Taxi Time: 2:35`, the saved time from here to there. A grey `Taxi Time: no time yet` means that trip has no saved time. There is no line on the node you stand at or on places you can't fly to.

`/tt tooltip` turns these lines off or on.

## Flight totals

A small line under the bar shows what this character has spent on flights and how long it has flown, like `Spent 12g 34s 50c | Flown 3h 12m`.

- The gold is what you really paid, so reputation discounts count. If the addon misses the payment, it uses the price on the map.
- Flown time counts every flight, also ones that are not recorded. Time logged out or on loading screens doesn't count.
- Counting starts the first time you log in with this version.

`/tt totals` prints the totals for this character and for all your characters, with the number of flights and the start date. `/tt totals off` hides the line under the bar, `/tt totals on` shows it again.

## Starter times and export

The addon can come with a list of known flight times, so the bar counts down even on your first flight of a route. In this version the list is still empty, so every new route starts with a recording flight.

Later, a time from the list shows with a `~` in front, on the bar and in the map tooltip. Your own first clean flight saves your time, and from then on your time is used. `/tt forget` goes back to the list's time.

`/tt export` opens a window with your saved times, ready to copy (Ctrl+C). It holds only node numbers and seconds: no names of characters or places. Times under 5 seconds or over 1 hour are left out.

To help fill the list, send your export in a [GitHub issue](https://github.com/gettic/TaxiTime/issues) or as a reply to Taxi Time's post on Discord. Send only your own export.

## Slash commands

Type `/tt` or `/taxitime`, followed by:

| Command | What it does |
|---|---|
| `unlock` | Unlocks the bar and shows a test bar, so you can drag it where you want. |
| `lock` | Locks the bar again. A locked bar lets clicks go through it. |
| `reset` | Puts the bar back in its default place (top middle of the screen). |
| `test` | Shows or hides a test bar. |
| `forget` | Forgets the saved time of the route you are flying or flew last. |
| `tooltip` | Turns the times on the flight map on or off. |
| `totals` | Prints gold spent and time flown. `totals on` / `totals off` shows or hides the line under the bar. |
| `export` | Opens a window with your saved times to copy. |

The bar starts locked. `/tt` on its own lists the commands.

## Chat messages

| Message | Meaning |
|---|---|
| `Recorded A > B: 2:05` | A new route's time was saved. |
| `Updated A > B: 3:40 -> 2:05` | A much shorter clean flight replaced a wrong saved time. |
| `Not recorded (reason): A > B` | This flight's time was not saved, and why. Only shown for a route without a saved time, or after a login during the flight. |

## Known limits

- There is no options window yet: the bar's size and colours can't be changed.
- `/tt forget` only knows routes flown since you last logged in or reloaded.
- After a login, a flight that started more than an hour ago is not shown again.
- If the game can't tell where you landed, the flight is trusted and saved.
- Early landings are only noticed if the game has the early-landing option.

## Art

All the addon's art (the bar frame, fill, flyers, cloud and sparkle) was drawn for Taxi Time. No Blizzard or other outside art is included. The script that draws it is in `art-source/` (see [its README](art-source/README.md)).

## For developers

| File | What it is |
|---|---|
| `TaxiTime/TaxiTime_Forever.toc` | Addon info: interface 16001, version, saved variables. |
| `TaxiTime/StarterTimes.lua` | The starter times list (empty in this version). |
| `TaxiTime/Core.lua` | Finds take-off and landing, saves route times, counts totals, the `/tt` command and export window. |
| `TaxiTime/Bar.lua` | The bar, the flyer, cloud, sparkle and the totals line. |
| `TaxiTime/Tooltip.lua` | The time line in the flight-map tooltips. |
| `TaxiTime/media/` | The art (`.tga` files). |
| `art-source/make_art.py` | Draws the art files. |

Saved data:

| Saved variable | Holds |
|---|---|
| `TaxiTimeDB` (account) | Route times, the bar's position, the tooltip and totals-line settings, and all characters' totals. |
| `TaxiTimeCharDB` (per character) | This character's totals, and the flight in progress, so it can be shown again after a login. |

The settings for recording (minimum flight time, the 80% rule, landing distance) are constants at the top of `Core.lua`. Setting `USE_CUSTOM_ART = false` at the top of `Bar.lua` switches to a plain look with the game's own icons, for example if the picture files don't load.
