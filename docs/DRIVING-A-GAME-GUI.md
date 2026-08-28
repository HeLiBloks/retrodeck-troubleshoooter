# Driving a game's GUI from an SSH session

Some faults only appear a few screens into a game — on a briefing, in a menu, after a
level loads. You cannot reason those out from a log, and you cannot ask a checker about
them, because **the game is the only thing that knows**. This is how to reach such a screen
from a shell, and where the method stops working.

It is a diagnostic aid, not a check: nothing here belongs in `rdtroubleshoot`, which reads
and never acts. Use it by hand when a symptom needs reproducing or a fix needs confirming.

> **You are driving somebody's actual desktop.** The pointer really moves, windows really
> take focus, and dialogs really appear on the screen in front of them. Say what you are
> about to do before you do it, keep it short, and stop when asked. If the user is sitting
> at the machine, asking them to click three times is faster and kinder than this.

## Reaching the display at all

An SSH session has no display, and getting this wrong produces a *different* failure that
looks like the one you are chasing:

```
Authorization required, but no authorization protocol specified
```

A game that prints that and exits 0 has not reproduced your bug — it never drew anything.
The seated session's X authority file is what you need, and on a Wayland desktop with
Xwayland it lives under the user's runtime directory:

```sh
ls /run/user/$(id -u)/xauth_*
export DISPLAY=:0 XAUTHORITY=/run/user/1000/xauth_XXXXXX XDG_RUNTIME_DIR=/run/user/1000
```

**Any run without this proves nothing.** It is the same shape of mistake as testing `PATH`
in a shell whose parent already exported it: the environment, not the program, produced the
result.

## Seeing what is on screen

The window list is often enough on its own, and it is the cheapest evidence there is — a
modal error dialog usually puts its whole meaning in the title:

```sh
xwininfo -root -tree | grep -iE '"<game name>"|error'
```

```
0x2600001 "Not Enough RAM": ("steam_proton" "steam_proton")  280x154+820+453
```

That single line established a diagnosis that three previous sessions had guessed at. Reach
for it before screenshotting.

For pixels, capture the game window by id rather than the root window:

```sh
import -window 0x1600008 /tmp/shot.png     # ImageMagick
```

Capturing a window that is grabbed by a modal child can hang; if `import` blocks, the grab
itself is the finding. Note that a window id changes between runs — re-read it from
`xwininfo` each time rather than reusing one.

## Clicking

Three things have to be right, and the first is the one that silently wastes an hour.

**1. Activate the window first.** Hover states will update without it, which is what makes
this so misleading — the cursor moves, buttons light up, and *clicks go nowhere*:

```sh
xdotool windowactivate --sync <winid>
```

**2. Move and click as separate, synchronised steps.** A combined `mousemove x y click 1`
fires the button before the game has processed the motion:

```sh
xdotool mousemove --sync 400 271
sleep 0.4
xdotool mousedown 1; sleep 0.15; xdotool mouseup 1
```

The explicit down/up with a gap survives engines that sample input on a frame boundary and
would miss an instantaneous click.

**3. Many list widgets need a double-click.** Selecting a row and confirming it are one
gesture in a lot of 1990s UIs — clicking the row then clicking the confirm button does
nothing, because the row was never committed:

```sh
xdotool mousedown 1; sleep 0.15; xdotool mouseup 1; sleep 0.2
xdotool mousedown 1; sleep 0.15; xdotool mouseup 1
```

## Finding the hotspots

You usually do not know where the buttons are. Two ways in, cheapest first.

**Hover and watch.** Most games highlight what is under the cursor, and many print the
name of the region somewhere fixed. Move, wait for a frame or two, capture, and read:

```sh
for p in "300 400" "700 500" "1100 300" "1500 400"; do
    set -- $p
    xdotool mousemove --sync "$1" "$2"; sleep 1.2
    import -window "$winid" /tmp/probe_$1_$2.png
done
```

Cropping each capture to the strip where the label appears and stacking them into one image
makes this one glance instead of many:

```sh
magick /tmp/probe_*.png -crop 1920x44+0+0 +repage -append /tmp/strip.png
```

**Read the coordinates off a screenshot.** Slower to set up but exact, and it is the only
option for a game that gives no hover feedback.

## Where this stops working, and what to do instead

- **Relative mouse input.** A game that grabs the pointer for camera control gets motion
  deltas, not positions, so `mousemove` to an absolute coordinate means nothing to it. Menus
  usually still take absolute input while gameplay does not — so you can often reach a
  screen and not get past it.
- **A command line that skips the thing you need.** Engines commonly offer a "jump straight
  into this level" flag, which sounds like exactly what you want and often bypasses the
  briefing, cutscene or menu that actually fails. Check what the flag *skips* before
  trusting it as a reproduction.
- **A first-run state you cannot get back.** Some faults only fire against a fresh profile.
  Once the game has written one, that path is gone until you move the profile aside.

When you hit one of these, stop automating and say so. A fix confirmed by the user playing
to the failing screen is worth more than an elaborate approximation, and **an unconfirmed
fix recorded as confirmed is the one outcome this repository exists to prevent**. Leave the
entry in `backlog/` and name the step you could not take.
