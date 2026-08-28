# retrodeck-troubleshoooter

Read-only diagnostics for **RetroDECK emulation and ROM-metadata scraping** on Fedora
Atomic (Bazzite, Kinoite, Silverblue).

Nothing here writes a file, spends API quota, or starts an emulator — so it is safe to run
while RetroDECK is open, which is exactly when you want to ask what is wrong.

Companion to a separate scraper project; this repository is what to reach for when
something is broken.

## Install

There is nothing to install. Python 3.11+ from the system, stdlib only:

```sh
git clone https://github.com/HeLiBloks/retrodeck-troubleshoooter
cd retrodeck-troubleshoooter
./rdtroubleshoot
```

That matters on an immutable host: deploying it is a file copy and nothing else.

### Optional: credentials for the privileged checks

A few questions cannot be answered as an ordinary user — the SELinux audit log under
`/var/log/audit` is root-only, and system Flatpak overrides live under `/var/lib/flatpak`.
Those checks are skipped by default and say so. To enable them:

```sh
cp .env_template .env
chmod 600 .env          # required: see below
$EDITOR .env            # set RDT_SUDO_PASSWORD
```

`.env` is gitignored and everything in it is optional. Two properties worth knowing before
you put a root password in a file:

- **A secret is never printed, never logged, and never placed on a command line.** Argv is
  world-readable through `/proc`, so the sudo password goes down the child process's stdin
  (`sudo -S`) and nowhere else.
- **A group- or world-readable `.env` is reported as a FAILURE and its secrets are
  refused.** Using them would tell you everything is fine while your root password sits in
  a file anyone on the box can read.

`./rdtroubleshoot env` shows which keys were found — names only, never values. `--no-env`
ignores the file entirely.

```sh
rsync -a --delete --exclude .git ./ retro@retrodeck-box:apps/retrodeck-troubleshoooter/
```

## Use

```sh
./rdtroubleshoot                      # every group
./rdtroubleshoot emulation input      # just these
./rdtroubleshoot -q                   # only what to act on
./rdtroubleshoot --json               # machine-readable
```

| group | covers |
|---|---|
| `env` | whether a `.env` was found, and which keys it supplies |
| `os` | SELinux mode and denials, ostree deployment, disks, Homebrew, distrobox |
| `flatpak` | app installs, whether each sandbox can reach the ROM tree, overrides |
| `emulation` | RetroDECK layout, gamelists, logs, BIOS, Switch, Model 3 |
| `input` | controllers — including the black-screen-after-loading cause |
| `scraping` | Skyscraper, credentials, resource cache, quota, per-tag coverage |

Exit **0** healthy, **1** warnings, **2** failures.

### Options

| flag | effect |
|---|---|
| `-q`, `--quiet` | only WARN and FAIL lines |
| `--json` | machine-readable output |
| `--show-benign` | include SELinux denials known to be normal on this host |
| `--probe-sandbox` | ask each Flatpak sandbox whether it can *really* read the ROM tree |
| `--repo PATH` | a retrodeck-scraper checkout, for `.env` and scrape logs |
| `--guid B V P V` | derive a Ryujinx controller id from four hex sysfs ids |
| `--no-color` | disable colour (also `NO_COLOR=1`) |
| `--no-env` | ignore any `.env`, and skip every check needing privilege |
| `--env-file P` | read credentials from `P` instead of `./.env` |

### Environment

| variable | default |
|---|---|
| `RETRODECK_HOME` | `~/retrodeck` |
| `RETRODECK_ROMS` | `$RETRODECK_HOME/roms` |
| `RETRODECK_ESDE` | `$RETRODECK_HOME/ES-DE` |
| `RDT_ENV_FILE` | `./.env` |
| `NO_COLOR` | unset |

## Example

```
== Host / Bazzite ==
INFO  Kernel           6.18.44-ogc1.1.fc44.x86_64 (Bazzite gaming kernel)
PASS  SELinux          enforcing (the expected state on Bazzite)
INFO  SELinux denials  N known-benign denial(s) hidden (sshd control socket)
PASS  SELinux denials  no unexplained denials this boot
PASS  Disk space       /var/home/retro/retrodeck on /dev/nvme0n1 (label RetroDECK) - plenty free
INFO  Homebrew         installed at /home/linuxbrew/.linuxbrew but not on PATH in a
                       non-interactive shell
                       -> eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)"

== Controllers / input ==
INFO  Pad detected     'Sony Interactive Entertainment DualShock 4' 054c:05c4 on js0 -
                       Ryujinx id 0-00000003-054c-0000-c405-000011810000
FAIL  Ryujinx input match  connected but no profile matches it - this is the
                           black-screen-after-loading symptom
```

## Why these particular checks

Every check stands for a failure that cost someone a session. A few, so you can judge
whether the tool is worth pointing at your machine:

- **A black screen after a game loads is almost always an unbound controller**, not the GPU.
  Ryujinx logs `Hid Remap: No matching controllers found` at *warning* severity while audio
  works and shaders compile, so everything looks alive. The pad can be plugged in and
  visible and still have no matching profile. The tool derives the id Ryujinx expects for
  every connected pad and compares it against the config.
- **`userCreds="user:"` is worse than anonymous.** A half-set ScreenScraper credential sends
  an empty password on every request; login is refused and the run scrapes nothing. It once
  cost a silent 4–5 hour unattended run, so it is reported as a failure, not a warning.
- **Quota exhaustion exits 0.** Every message ScreenScraper's client prints before giving up
  leaves the status at zero, so log text is the only signal there is.
- **`/home/retro` and `/var/home/retro` are the same directory and not
  interchangeable.** ES-DE and Skyscraper match gamelist entries by the raw path string;
  mixing the spellings drops entries on the next generate. Every gamelist is checked.
- **A gamelist can legitimately have two root elements**, which every plain XML parser
  refuses. ES-DE writes `<alternativeEmulator>` beside `<gameList>` when an emulator
  override is set; calling that corrupt reports a fault on a working system.
- **Descriptions were never the whole gap.** One library read 98% described and 45%
  un-genred at the same time. Coverage is counted per tag, worst system first.

...and, as much to the point, which normal-looking alarms it refuses to raise: `/` is 100%
full on every ostree host for ever, SELinux denies sshd a control socket on every SSH
connection, and Homebrew is invisible in a non-interactive shell. A checker that fires on
those teaches you to ignore its exit code.

## The knowledge base

A problem diagnosed once should stay diagnosed, so findings live in `docs/kb/` as entries —
and the entries are **executable**: each carries machine-matchable signatures, so a log can
route itself to the answer.

```sh
rdtroubleshoot kb search "black screen"     # what is already recorded?
rdtroubleshoot kb match <log>               # route a log to entries
rdtroubleshoot --kb                         # annotate each WARN/FAIL with its entries
```

That last one is the payoff. A real warning on a live machine comes back knowing what it is:

```
WARN  Ryujinx sandbox  ~/retrodeck/roms is reachable read-only via 'home:ro'; writes beside the ROM will fail
                       -> flatpak override --user --filesystem=~/retrodeck io.github.ryubing.Ryujinx
                       known issue [fix known]: ryujinx-saves-lost-sandbox-home-readonly
                         docs/kb/errors/flatpak/ryujinx-saves-lost-sandbox-home-readonly.md
```

**Two states, one gate.** `backlog/` is a case with no verified fix; `errors/` is a case with
one. The test: if you can tell somebody what to *do*, it belongs in `errors/`. Promotion is
the only gated step, and the gate is enforced by code — a `verified:` date, a `verified_by:`
record of how it was confirmed, an eval fixture, a clean lint and a green suite.

"Known, no fix yet" is a real answer, and a much better one than an invented fix. A
well-recorded unsolved case is a genuinely useful contribution.

Areas are `os`, `flatpak`, `emulation`, `input`, `scraping` — exactly the checker's group
names, which is what lets a failing check point at the entries that cover it.

See [docs/kb/README.md](docs/kb/README.md) for the lifecycle, the frontmatter subset and the
signature sources, and [CONTRIBUTING.md](CONTRIBUTING.md) to add one.

## Documentation

| file | contents |
|---|---|
| [docs/EMULATION.md](docs/EMULATION.md) | logs, the black-screen case, Switch, Model 3, gamelist traps |
| [docs/BAZZITE-OS.md](docs/BAZZITE-OS.md) | SELinux, Flatpak sandboxes, ostree, brew, udev, this machine |
| [docs/SCRAPING.md](docs/SCRAPING.md) | failures that report success, quota, coverage, source invariants |
| [docs/kb/README.md](docs/kb/README.md) | the knowledge base: lifecycle, frontmatter, signatures |
| [CONTRIBUTING.md](CONTRIBUTING.md) | adding an entry, and the direct-push vs pull-request rule |
| [CLAUDE.md](CLAUDE.md) | the agent contract, and the record of what was measured |

## Working with an agent

The repository is set up for both Claude Code and Codex. `AGENTS.md` is a symlink to
`CLAUDE.md`, so both read the same bytes, and the four skills are listed in that file
because Codex has no `.claude/skills` equivalent — the list *is* the discovery mechanism for
half the agents working here, and a test fails if a skill is missing from it.

| skill | for |
|---|---|
| `diagnose-emulation` | a game that will not launch, a black screen, missing art, a pad |
| `diagnose-scraping` | a scrape that produced nothing, thin or wrong metadata, quota |
| `diagnose-host` | SELinux, Flatpak sandboxes, ostree, brew, distrobox, disks |
| `read-retrodeck-logs` | reading the logs correctly — rotation format, noise, key lines |
| `kb-lookup` | the dedup pre-flight: is this already recorded? |
| `document-finding` | record a finding, and commit or open a PR for it |

## Developing

```sh
./tools/check.sh                        # compile + suite + CLI smoke
python3 -m unittest discover -s tests -b
```

The suite needs neither the network nor a RetroDECK install. Run the CLI on a machine
*without* RetroDECK too — that is what proves every check degrades to INFO instead of
crashing, and it is how two of the three defects in the first draft were found.
