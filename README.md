# Agent Android (net.sys32.agent)

---

## What this agent is

`net.sys32.agent` **is not a browser chatbot and it is not a thin client**. It is an
autonomous AI agent that runs **on the phone itself**, with access to your device at a
level almost no ordinary app has.

When you ask it for something, it does not forward the request somewhere to get text
back — it **executes**. It reads sensors, takes a real GPS fix, opens the camera,
compiles code, installs apps, writes to the screen, reads other apps' notifications,
drops into a Linux terminal and runs commands there. The app is the terminal; the agent
is the operator.

**Mandatory requirements, before anything else:**

1. **ADB running on the phone** — the app talks to the Android system through `adbd`
   on `127.0.0.1:5555`. Without ADB, **you cannot even install this app**: the 2.4 GB
   APK must go through `adb push` + `pm install`, because Android refuses to install it
   from the UI or from `/sdcard`. And without ADB half the capabilities do not exist
   either: no `pm install`, no `dumpsys`, no `settings put`, no UI automation.
   See [Step 5](#step-5--the-phone-developer-mode--usb-debugging) and
   [Step 6](#step-6--connection-adb--tcpip-5555).
2. **DeepSeek API key** — the agent is driven by a language model. Without a key the
   app starts and extracts its environment, but **it cannot think**: you get no answer
   to any command. Get a key at <https://platform.deepseek.com> and enter it on first
   launch. See [Step 8](#step-8--first-launch-inside-the-app).

Without these two, the rest of this document will not help you.

---

## Why this app is unusual

Not "another AI app". What follows is what actually runs on the phone, measured — not
marketing.

### It carries its own compiler

Most mobile AI apps send a request and print the answer. This one **compiles code on the
device**: clang 21 + lld + Android sysroot + NDK, Rust (rustc + cargo), CMake, ninja,
make, perl, FLANG for Fortran.

The practical consequence: `pip_install` builds C/C++ extensions **natively on the
phone**. lxml, numpy, Pillow, zstandard were each verified end-to-end this way. And
`build_apk` compiles **entire Android APKs on the phone** — Gradle + AGP + JDK + aapt2,
offline, no PC.

That is the first thing that makes it different: it is not a consumer of software, it
is a producer of it.

### A real Linux, that is not cut off from Android

Inside the app runs **Debian 13 arm64 through proot** — a working `apt`, `gcc`,
`python3`, `git`, `nano`, `htop`.

The usual assumption is that a Linux container on Android is blind to the hardware. Here
it is not. Through an internal bridge (TCP loopback, one JSON line per request) Debian
reaches the Android SDK:

```
eval call ctx.getSystemService(wifi)   ->  android.net.wifi.WifiManager  (real object)
sensors read accelerometer             ->  live x/y/z values
```

So a Python script inside Debian can read sensors, take a photo, control the UI. Not a
sandbox pretending to be a computer — a Linux that kept its hands on the phone.

### It speaks to Android services at protocol level

Not through an API someone wrapped for it. The app opens `/dev/binder` directly and
performs **IPC calls against Android system services**: 466 services enumerated, AIDL
descriptors resolved, real calls verified against `display`, `input`,
`batteryproperties`. A second path (reflection) reaches **any class and method in the
SDK**, including live objects and listeners.

This is the layer where most "AI phone assistants" stop and hand you a settings deep
link. Here it is an actual call.

### Three independent ways to reach the system

Redundancy is deliberate, because each one fails where another works:

- **ADB** (`uid=2000` shell) — `pm install`, `dumpsys`, `settings put`, `input`,
  `screencap`, `logcat`. This is system-administrator reach from inside a normal app.
- **Reflection** — anything the SDK exposes to an app, including classes without a
  convenient wrapper.
- **Native Binder** — no adb, no bridge, straight to the service.

When ADB is not authorised, reflection still works. When a service is lazy and not
registered, reflection instantiates it. When you need `pm install`, only ADB will do.

### Voice that never leaves the phone

`/audio on` gives hands-free operation, and **nothing is uploaded**:

- **Whisper `medium`** (1.5 GB) via natively compiled `whisper.cpp`. `medium` and not
  `small` for a measured reason — `small` mangles Romanian words.
- **Phonon 31m** (61 MB) for offline text-to-speech.

Both run locally. No network dependency, no audio sent anywhere.

### It maintains itself

- **Self-heal** on every start: dead symlinks after an APK update, truncated packages
  shadowing the app zip, CA bundle, git identity, sysconfig paths — repaired
  automatically.
- **Persistent memory**: lessons written to `memory.md`, loaded at start.
- **Skills**: 12 saved procedures that load only when relevant, so a past session's
  hard-won knowledge does not have to be rediscovered.

### It writes its own skills and memories

This is not a static tool. After working, the agent decides by itself what is worth
keeping — and saves it without being asked.

**Skills are saved automatically** (`/autoskill`, ON by default, threshold 6 tool steps).
When a task takes 6 or more tool steps, the agent gets one extra turn that asks a single
question: *did this produce a reusable procedure or a pitfall worth keeping?*

- If yes → it writes `skills/<kebab-name>/SKILL.md` with the format `When to Use` →
  `Method` (exact commands) → `Pitfalls` (trap → fix)
- If the topic is already covered → it **patches the existing skill** instead of creating
  a near-duplicate
- If the task was routine → it answers exactly `SKIP` and writes nothing

The rule enforced in the prompt is strict: *cite only commands and errors you really
ran; never invent paths, packages or flags.* That is why skills are worth loading — they
contain what actually worked **on this device**, not generic advice.

Next session, the skills index is injected into the system prompt. When a task looks
even partially relevant, the matching skill is loaded and followed.

**Memory is reviewed autonomously** (`/auto-learn`, ON by default, every 10 turns). An
isolated review pass looks at the recent conversation and decides whether anything
durable emerged:

- **What belongs in memory**: durable facts true in *every* session — how the operator
  works and what they expect, plus facts about this device (hardware quirks,
  Android/SELinux behaviour, adb powers and limits, working paths)
- **What does not**: procedures (those are skills), transient errors, one-off task
  narratives, negative claims about tools, environment misses the operator can fix
- **Format**: one line per lesson, telegraphic —
  `TRAP: what failed -> error -> cause -> fix`, `OK: what works`, `DEAD: what does not -> proof`,
  `P: path -> artifact`, `RULE: 1 -> 2 -> 3`

Before writing, it re-reads the current `memory.md` and refuses to add a fact already
covered, even in different words. If a bullet went stale, it is fixed in place.

**You can also trigger both manually:**

- **`/learn`** — update memory now, on demand
- **`/autoskill [N]`** — toggle self-saving skills, optionally change the step threshold
- **`/auto-learn [N]`** — toggle the autonomous memory review, optionally change the interval
- **`/skill [name]`** — list saved skills, or load one into context
- **`/curator`** — archive skills that are no longer used (recoverable in `skills_archive/`)
- **`/mem`** — memory statistics: size, bullets, density, lint

Everything is plain text on disk, in the app's private storage — inspectable and
editable by you at any time, no database, no lock-in.

### Numbers, not adjectives

Every claim above comes with a measurement in
[TECHNICAL_REFERENCE.md](TECHNICAL_REFERENCE.md) — on a Samsung SM-A366B, Android 16,
no root. Including the ones that did not work out, and the conclusions that were wrong
and later corrected.

**45 slash commands, 22 tools, 12 skills, 466 binder services, 8439 toolchain files,
2.4 GB APK.** The size is the honest part: everything listed here is actually inside the
file you download.

---

## Linux (Debian) that installs itself — no root, no PC

The first time you launch the app, it provisions a complete Debian 13 environment **by itself**
and shows the progress in the terminal. Measured end to end on **Xiaomi 2409FPCC4G (Android 16,
no root)** and **Samsung SM-A366B**: **48 s / 108 s**, one time only.

```
[done] Linux filesystem - Debian 13.7
[done] Linux runtime - proot ready
[done] Linux runtime - Debian 13.7, Python 3.13.5
[done] Android service access - CONCLUZIE: binder-ul FUNCTIONEAZA ... 236 servicii accesibile
READY !
```

Inside you get a real shell with **Python 3.13.5, gcc 14.2, make, git, curl** and a precompiled
native Binder client — no downloads on the phone, everything comes from the APK (187 MB image).

### What you have to do once

**Turn on USB debugging and accept the "Allow USB debugging" dialog.** That is all. If it is not
authorised yet, the app writes exactly what is missing in the terminal and **retries by itself**
for up to 3 minutes — you do not have to type `setup` again.

### Why that one dialog cannot be skipped

Measured on the phone, not assumed:

| Attempt | Result |
|---|---|
| app process runs `proot` on a rootfs in its own files | `avc: denied { setattr } proc/fd` + `execve: Permission denied` |
| app process runs `proot` on a rootfs in `/data/local/tmp` | `avc: denied { search } shell_test_data_file` |
| app writes into `/data/local/tmp` | `Permission denied` (owned by `shell`) |
| adbd reads the app's private files | `Permission denied` (SELinux) |
| adbd reads the APK's native library dir | **yes** (that is why the image ships in `lib/arm64`) |
| adbd runs `proot` from `/data/local/tmp` | **yes** (the only path that works) |

Android's SELinux policy forbids an app from executing a Linux userland. The Android shell (adbd)
is the only bridge — on every phone, rooted or not. That is a kernel policy, not something an app
can work around.

### Compatibility

| | Xiaomi (no root) | Samsung | any Android 26+ |
|---|---|---|---|
| one-time USB debugging dialog | needed | needed | needed |
| everything else (download, extract, proot, binder) | automatic | automatic | automatic |
| speed | internal f2fs, same as Samsung | internal f2fs | identical |

The old code path (`proot_tool.py`) is **untouched**: the new installer lives in
`proot_tool_xiaomi.py` and is only used when the APK actually contains the image, so existing
installations cannot regress.

---

## Command reference

Type `/help` (or `/?`) in the app for this list. Everything below runs locally — a slash
command costs zero tokens unless noted.

### Memory and learning

- **`/learn`** — update memory now (manual learning). Reviews the session and appends
  durable facts to `memory.md`.
- **`/autoskill [N]`** — toggle self-saving skills. `N` = minimum tool steps before the
  agent considers writing one (default 6, currently ON). The agent may answer `SKIP`.
- **`/auto-learn [N]`** — toggle the autonomous memory review that runs every N turns
  (default 10, currently ON). Alias: `/autolearn`.
- **`/skill [name]`** — with no argument, list saved skills; with a name, load that
  skill's full text into context.
- **`/curator`** — archive skills that are no longer used. Recoverable in
  `skills_archive/`.
- **`/mem`** — memory statistics: size, bullet count, density, lint warnings.

### Context and cost

- **`/ctx`** — context window usage, token counts, cache hit ratio, and how many archives
  and tool logs are on disk. *Nothing is ever deleted, only moved to disk.*
- **`/compact`** — compress the context now. **Disabled by the operator** in this build:
  the context is never compressed automatically, so the memory loaded at startup stays
  intact until `/reset`.
- **`/insights`** — tokens, cache, estimated cost, most-used tools.
- **`/title`** — show this session's title (derived from your first message).
- **`/reset`** — erase the conversation history.

### Execution and environment

- **`/run <script.py>`** — run a script from the workspace **with the app's rights**
  (`uid=app`). Cannot see `/data/local/tmp`.
- **`/run_su <script>`** — run a script with **shell rights** (`uid=2000`). Needed for
  `/data/local/tmp`, the native toolchain, llama.cpp, GGUF models, compiled binaries.
- **`/heal`** — repair the environment now: launchers, shadowed packages, `pip.conf`.
  Costs 0 tokens.
- **`/audit`** — report what is broken right now, **without repairing it**. 0 tokens.
- **`/selfheal`** — show or hide the "environment healthy" line at startup. Alias:
  `/self-heal`. 0 tokens.
- **`/where`** — show every location: home, workspace, memory, context, logs, archive.

### Safety

- **`/safe`** — guardrails ON (the default). Refuses hardline commands and writes to
  system or credential paths.
- **`/unsafe`** — guardrails OFF, runs anything. **Not saved to disk**: a restart returns
  to SAFE. Redaction of secrets in tool output stays ON regardless.

### Interface

- **`/verbose`** — toggle full code and output of every step.
- **`/nospin`** — no live status line at all; clean scrollback (best on a phone).
  `/spin` turns it back on.
- **`/watch [sec]`** — one status line every N seconds, **only while a job runs**. Costs
  0 tokens (it writes to the screen, not into the model context).
- **`/audio on`** — **turn on persistent audio mode.** Every reply from then on is
  spoken aloud and **not printed on screen**: clean prose, no markdown, no lists, no code
  blocks, no emoji. An `AUDIO MODE` panel appears with a push-to-talk button and an
  `EXIT AUDIO MODE` control. The model is instructed to answer in **English only** while
  audio mode is on, regardless of the language you write in — that is what the voice
  engine pronounces cleanly.

  ```
  /audio on           ->  [audio] ON: every reply is spoken, nothing is shown.
  <anything>          ->  spoken aloud, not displayed
  /audio off          ->  back to normal text output
  ```

- **`/audio`** (with no argument, or `/audio arm`) — same thing: turns persistent audio
  mode on.

- **`/audio <message>`** — turns audio mode on **and** sends that message immediately.

  ```
  /audio what is my battery level
  ```

- **`/audio off`** — leave audio mode. Alias: `/text`.

> **This is what makes the phone hands-free.** With a headset or just the speaker you can
> work without looking at the screen. Combined with push-to-talk (the voice button in the
> audio panel, Whisper local STT), the whole loop stays on the device: you speak, it
> transcribes locally, the agent acts, the answer comes back through Phonon. Nothing is
> uploaded — no audio, no text, no cloud.

- **`/todo`** — show the current task list.
- **`/help`**, **`/?`** — the command list.
- **`/exit`**, **`/quit`** — leave (an empty line does nothing, it does not quit).

> **`/safe` vs `/unsafe` in practice:** the guardrails block writes to `/system`,
> `/vendor`, `/proc`, `/sys`, `/dev/block`, `/data/system` and similar, plus any path
> that looks like a credential file — including paths *built from variables*. The refusal
> is visible (yellow). You can unlock with `/unsafe`; every hardline command then runs
> with a red `[UNSAFE]` audit line in the log.

---

## Do not update your phone's OS


This is the section to read before anything else if you are about to accept a system
update.

### The app was built and tested on one specific version

```
Android 16  ·  SDK 36  ·  security patch 2025-11-01
samsung/a36xqnaeea/a36xq:16/BP2A.250605.031.A3/A366BXXU5BYK5_OXM5BYK5:user/release-keys
Samsung SM-A366B
```

Every measurement in this project — 467 binder services, 29 sensors, the `uid=2000`
shell, the Debian rootfs, the native toolchain — was taken on **that** build. It is not
an estimate of what might work elsewhere; it is what was actually verified.

**We do not recommend upgrading to a newer Android version.** The app may break, and
there is no fallback: you cannot downgrade Android on a locked bootloader.

### Google has already moved against autonomous agents on Play Store

This is not speculation — it is published policy. From the Play Console Help page on
`AccessibilityService` use:

> Any use of the Accessibility API that enables an app to **autonomously initiate, plan,
> and execute actions or decisions is strictly prohibited.** This does not prohibit
> deterministic, rule-based automation, where behavior follows a static, human-defined
> script.

Read that carefully: it does not ban automation. It bans exactly what an autonomous
agent does — planning and deciding by itself. A script that follows a fixed sequence is
fine. An agent that reads the screen, decides what to do next and executes is not.

Note also the exemption clause: apps flagged `isAccessibilityTool="true"` escape the
prohibition *"provided this functionality is for the app's core purpose"*. That is a
narrow door, and it exists to protect screen readers, not agents.

**This app is distributed outside Play Store for that reason.** Not because it was
rejected — because the policy it would be judged by is directly at odds with what the
app is.

### The direction of travel is clear

Google is openly building "agents in Android" as a first-party feature — you can see it
on developer.android.com today: *"Turn prompts into real Android experiences using your
favorite agents."*

When a platform ships its own agent, the natural next step is to **constrain what
third-party agents can do**, so that the first-party one is the sanctioned path. That
pattern has repeated on every platform: a capability is open, then it becomes gated,
then it becomes privileged.

Expect the following to tighten in upcoming OS versions:

- **AccessibilityService** — already restricted by policy, technically auditable
- **`adb tcpip` / wireless debugging** — increasingly gated behind per-session pairing
- **`MANAGE_EXTERNAL_STORAGE`** — repeatedly narrowed
- **Background execution and foreground services** — the most aggressively restricted
  area of the last four Android releases
- **Side-loading** — the direction is toward friction, verification and consent walls

Any one of these breaking removes a whole group of capabilities from the app. `adb`
alone carries half of them.

### Practical recommendation

1. **Do not accept system updates** on the phone that runs this agent. Turn off
   automatic updates: *Settings → Software update → disable auto-download/install*.
2. **Keep the build that was tested.** `A366BXXU5BYK5` with security patch 2025-11-01.
3. **If you must update**, do it on a device you can afford to lose this app on — and
   verify afterwards that ADB still authorises, `binder` still lists ~467 services, and
   `toolchain selftest` still passes.
4. **A dedicated phone is the sane setup.** A cheap spare device, kept on a known OS
   version, used only for this.

> Security patches do matter. The trade-off here is explicit: you are choosing a working
> autonomous agent on a slightly older build over a patched build on which it may stop
> working. Decide with open eyes, not by accident during a routine update prompt.

---

## Two ways to get the app — pick one

### Option 1 — the precompiled APK (recommended, works out of the box)

**The app is already built and ready to use.** You do not need a laptop, a JDK, an
Android SDK or Gradle to run it. Download one file and install it:

```
https://sys32.net/dist/net.sys32.agent.apk
```

This is the **out-of-the-box** path. Everything is already inside the APK: the Python
runtime, the native toolchain, the Debian rootfs, the Whisper and Phonon models.
Nothing has to be compiled.

**It still requires setup on the phone** — a precompiled APK removes the build step,
not the configuration:

- **ADB is MANDATORY** — the APK can be installed no other way (see below)
- all runtime permissions must be granted on first launch
- a DeepSeek API key must be entered

See [Step 5](#step-5--the-phone-developer-mode--usb-debugging),
[Step 6](#step-6--connection-adb--tcpip-5555),
[Step 7](#step-7--installation) and
[Step 8](#step-8--first-launch-inside-the-app). Skip Steps 1-4 entirely.

#### Mandatory: the precompiled APK is installed ONLY through ADB

**You cannot install it by tapping the file on the phone.** No file manager, no
"Install from unknown sources", no copying the APK to the device and opening it. That
path does not work for this app, for two independent reasons:

1. **Size — 2.4 GB.** The Android UI installer is built for apps of tens or hundreds of
   MB. At this size it runs out of memory and time and aborts with a generic
   **"App not installed."**, with no useful detail.
2. **Location — Android 16 refuses APKs from `/sdcard`.** Even a small APK fails when
   opened from `Downloads`, because the file has the SELinux context
   `u:object_r:fuse:s0` and `system_server` cannot read it.

So the phone must be reachable over ADB, and the install runs through `pm install`:

```bash
# one-time on the phone: enable developer mode -> USB debugging, then plug the cable
adb tcpip 5555                                    # optional: go wireless afterwards
adb connect 192.168.1.100:5555                    # optional: no cable needed

adb push net.sys32.agent.apk /data/local/tmp/agent.apk
adb shell pm install -r -g /data/local/tmp/agent.apk
# -> Success
```

`/data/local/tmp` is the **only** directory `pm install` accepts — the app's own
storage is not even readable by `system_server`. Full detail and four install variants
(USB, Wi-Fi, download-on-phone, from inside the app) in
[Step 7](#step-7--installation).

> **Bottom line:** no ADB, no installation. A phone without ADB cannot run this app,
> precompiled or not.

### Option 2 — clone the repo and build from source

**The role of the cloned repo is to make modifications.** If you want to change the
code — the Python agent, the Kotlin layer, the assets, the build config — this is the
path. Steps 1-4 walk through cloning, bootstrapping the binaries from the APK, setting
up the toolchain and building a new APK with Gradle.

The repo does **not** contain the precompiled APK (2.4 GB does not belong in git) and
does not contain the large binaries either. That is exactly why
`tools/bootstrap_binaries.sh` exists: it pulls them out of the published APK so the
build has something to package.

**Summary:** the VPS APK is for using the app. The repo is for changing it.

---

## What it can do

### Full Android access, through ADB (uid 2000)

The agent ships a Python ADB client that authenticates into `adbd` over loopback. The
result is a **privileged shell** (`uid=2000(shell)`) inside the app:

- `pm install` / `uninstall` / `grant` / `revoke` / `clear`
- `settings put global` — changes system settings and reads them back
- full `dumpsys` — activity, battery, wifi, sensorservice, package
- `input tap` / `swipe` / `keyevent` — controls any app, without accessibility
- `screencap`, `uiautomator dump`, `logcat`, `am start` / `force-stop`
- `service call` — direct calls into system services

On top of that, a second channel: **reflection**. The evaluator in `Reflection.kt`
gives access to **any class and method in the Android SDK** — `getSystemService`,
calls on live objects, object instantiation, listeners. You are not limited to
whatever a prepared API happens to expose.

### Native Binder — no adb, no bridge

The app opens `/dev/binder` directly and speaks to Android services at protocol level.
**466 services** enumerated, AIDL descriptors resolved, real calls verified
(`display`, `input`, `batteryproperties`). This is not a cosmetic list: these are
actual IPC calls.

### A fully functional Debian 13, with TOTAL access to Android

Inside the app there is a **real Linux terminal** — Debian 13 arm64, through proot.
Not an emulation, not an empty sandbox: working `apt`, `gcc`, `python3`, `git`, `nano`,
`htop`.

The important part, and the one that surprises people: **Debian is not blind to
Android.** It reaches the hardware and the SDK through the internal bridge
(AndroidBridge, TCP loopback):

- `eval call ctx.getSystemService(wifi)` → a real `android.net.wifi.WifiManager`
- sensors with **live** values, battery, camera, clipboard, UI
- arbitrary reflection — the same capabilities as the agent, from inside Linux

So you can write a Python script in Debian that reads sensors and controls the phone.
What Debian **cannot** do: read `/data/data/<other package>` (SELinux) and obtain root
(there is no `su` on the device). Otherwise, access is complete.

### Audio mode — you speak, you don't type

`/audio on` opens the voice screen. Hold the button, speak, release.

**Speech-to-text: Whisper, local.** The `medium` model (1.5 GB) runs **on the phone**,
via natively compiled `whisper.cpp`. Nothing leaves the device. `medium` was chosen
over `small` for a measured reason: `small` mangles Romanian words.

**Text-to-speech: Phonon, local.** A 31m model (61 MB), offline voice. The reply is
spoken, not printed.

Both are **offline and private**. They do not depend on the network after setup.

### Native compilation toolchain

A complete toolchain lives on the phone, inside the app:

- **clang 21**, lld, Android sysroot, NDK
- **Rust** (`rustc` 1.98.1, `cargo`), **maturin**
- **CMake 3.31.6**, **ninja**, **make**, **perl**
- **FLANG** (Fortran) — functional through the wrapper in `files/tmp`

The consequence: the app **compiles code on the phone**, including C/C++ extensions for
Python (`pip_install` with native compilation) and **entire APKs** (`build_apk` —
Gradle + AGP + JDK + aapt2, all on device, no PC).

### 22 tools, one agent

The agent has at its disposal: `python`, `bash`, `smart`, `read`, `multi`, `run_code`,
`todo`, `skill`, `scraper`, `android`, `androidapi`, `adbsh`, `binder`, `bridge`,
`terminal`, `build_apk`, `toolchain`, `bg`, `delegate`, `moa`, `look`, `help`.

The ones that matter for raw power: **`delegate`** (isolated subagents, in parallel),
**`moa`** (several independent attempts at a hard question), **`bg`** (long jobs in the
background), **`run_code`** (one script calling the other tools).

### Web, memory, self-learning

- **`scraper`** — lxml, parsel, trafilatura, quickjs, feedparser, all native on device
  Fifteen modes: `article`, `xpath`, `css`, `table`, `links`, `meta`, `sniff`, `rss`, `js`,
  `deep`, `jsdata`, `supreme`, plus `fetch`/`head`/`health`. Full reference, the silent
  brotli trap and the 15/15 verification battery: [`docs/SCRAPER.md`](docs/SCRAPER.md)
- **Skills** — saved procedures that load automatically when relevant
- **Memory** — persistent lessons, written via `/learn`
- **Self-heal** — repairs its own environment on every start (dead symlinks, truncated
  packages, CA bundle, git identity)

### What it CANNOT do

Honestly, so you don't waste time:

- **No root.** There is no `su` on the device; `user` build, `ro.secure=1`
- **Cannot read `/data/data/<other package>`** — SELinux `untrusted_app` / `shell:s0`
- **No ARP or SYN scan** — CapEff=0, capabilities are zero in every context
- **Cannot run its own Java code from a shell** — ART does `chown` at startup,
  structurally blocked

---

## Table of contents

**To just use the app:** [Option 1](#option-1--the-precompiled-apk-recommended-works-out-of-the-box)
→ Steps 5, 6, 7, 8. Skip everything else.

**To modify the code:** continue in order.

1. [What you need](#1-what-you-need)
2. [Step 0 — The original APK (MANDATORY)](#step-0--the-original-apk-mandatory)
3. [Step 1 — Clone](#step-1--clone)
4. [Step 2 — Bootstrap (the .sh script)](#step-2--bootstrap-the-sh-script)
5. [Step 3 — Build environment on the laptop](#step-3--build-environment-on-the-laptop)
6. [Step 4 — Build the APK](#step-4--build-the-apk)
7. [Step 5 — The phone: developer mode + USB debugging](#step-5--the-phone-developer-mode--usb-debugging)
8. [Step 6 — Connection: adb + tcpip 5555](#step-6--connection-adb--tcpip-5555)
9. [Step 7 — Installation](#step-7--installation)
10. [Step 8 — First launch inside the app](#step-8--first-launch-inside-the-app)
11. [Final verification](#final-verification)
12. [Quick troubleshooting](#quick-troubleshooting)

---

## 1. What you need

### Two things without which nothing works

| Requirement | Why it is mandatory | Where to solve it |
|---|---|---|
| **ADB running** | half the capabilities go through `adbd`, and **the APK can ONLY be installed this way** | Step 5 + 6 |
| **DeepSeek API key** | without a model, the agent cannot think | Step 8 |

The rest are ordinary technical conditions, listed below.

> **The APK is installed EXCLUSIVELY through ADB.** It is 2.4 GB, and Android cannot
> install a file that size from the UI — nor from `Downloads`, because of the SELinux
> context. There is no "tap the APK" shortcut. All methods go through
> `adb push` + `pm install`; four variants, in Step 7.

### On the phone

- **Android 8.0+** (`minSdk 26`); tested on Android 16 (`targetSdk 36`)
- **arm64-v8a** (any modern phone). x86_64 also exists for the emulator
- **~8 GB free space** — the APK is 2.4 GB, and the first launch extracts another
  ~1.5 GB into the app's internal storage
- **~4 GB RAM** recommended

### On the laptop

- **Windows / macOS / Linux** — the build is identical, only paths differ
- **~15 GB free space** (repo + APK + Gradle cache)
- **Internet** for the first build (Gradle dependencies, ~500 MB once)

---

## Step 0 — The original APK (MANDATORY)

**This is the part that cannot be skipped.** The large binary files are **deliberately
absent** from the repo — they don't fit in git:

| What is missing | Size | Where it comes from |
|---|---|---|
| `assets/toolchain/` | ~1056 MB | extracted from the original APK |
| `assets/android_build/` | ~399 MB | extracted from the original APK |
| `assets/models/` (voice) | ~63 MB | extracted from the original APK |
| `assets/whisper/models/` | 1.5 GB | extracted from the APK **or** downloaded |
| `assets/proot/` | ~var | extracted from the original APK |
| `jniLibs/*.so` | ~24 MB | extracted from the original APK |

All of them live **inside an already built APK**. That is why you need one.

### Where to get the APK — direct link

**Download it here:**

```
https://sys32.net/dist/net.sys32.agent.apk
```

```bash
mkdir -p dist
curl -L -o dist/net.sys32.agent.apk https://sys32.net/dist/net.sys32.agent.apk
```

Or with resume from where it stopped (recommended for 2.4 GB):

```bash
curl -L -C - -o dist/net.sys32.agent.apk https://sys32.net/dist/net.sys32.agent.apk
```

Or with `wget`:

```bash
wget -c -O dist/net.sys32.agent.apk https://sys32.net/dist/net.sys32.agent.apk
```

**Size:** 2,675,243,215 bytes (2.4 GB)

**Verify integrity** after downloading — if the hash does not match, the download is
corrupted and bootstrap will fail in ways that are hard to diagnose:

```bash
sha256sum dist/net.sys32.agent.apk
# expected:
# f0872546b9d56c23d9478ec2222c7ec8f460f2543ddb28cc021d3fb197246a35

# and confirm this build really carries the automatic Linux installer:
unzip -l dist/net.sys32.agent.apk | grep -E 'proot_tool_xiaomi|libagentroot_exec'
#   assets/python/proot_tool_xiaomi.py            <- no-root installer
#   lib/arm64-v8a/libagentroot_exec.so            <- the 187 MB Debian image
```

```bash
# macOS
shasum -a 256 dist/net.sys32.agent.apk
```

```powershell
# Windows
Get-FileHash dist\net.sys32.agent.apk -Algorithm SHA256
```

> **No APK?** You cannot bootstrap from scratch, because the native toolchain
> (clang, sysroot, Rust) would have to be compiled from source — a process of several
> hours on a powerful laptop. The APK is the normal path, not a shortcut.

### Where to put it

**Exactly in `dist/`**, at the root of the cloned repo:

```
android_agent/
└── dist/
    └── net.sys32.agent.apk      <- HERE (the name does not matter, the extension does)
```

```bash
mkdir -p dist
ls -lh dist/net.sys32.agent.apk   # check: 2.4 GB
```

`dist/` is in `.gitignore` — the APK stays local, it is not uploaded to git.

### Verify the APK BEFORE bootstrap

A truncated APK (interrupted download) produces cryptic errors later. Test it:

```bash
unzip -t dist/net.sys32.agent.apk | tail -3
# expected: "No errors detected in compressed data of dist/net.sys32.agent.apk."
```

If `unzip -t` reports errors → **download again**. Do not continue.

---

## Step 1 — Clone

```bash
git clone https://github.com/fetidness/android_agent.git
cd android_agent
```

The repo is ~100 MB (history) with ~1400 files.

If you use SSH:

```bash
git clone git@github.com:fetidness/android_agent.git
```

---

## Step 2 — Bootstrap (the .sh script)

This is **the only hard step**, and it does everything: it extracts the binaries from
the APK into the correct places in the source tree.

### Run it

```bash
cd android_agent
bash tools/bootstrap_binaries.sh
```

> **Disaster scenario** — you only have the git repo and a debug APK, everything else is
> gone. See [`docs/RECOVERY_FROM_GIT_AND_APK.md`](docs/RECOVERY_FROM_GIT_AND_APK.md) for the
> full procedure, verified end-to-end (5 minutes on a clean clone).

The script looks for the most recent `.apk` in `dist/` automatically — **it does not
need a phone, it does not need adb**. You can run the whole thing on the laptop,
offline once you have the APK.

### What it does, in order

| # | Extracts | Destination | Size |
|---|---|---|---|
| 1 | `lib/arm64-v8a/*` | `app/src/main/jniLibs/arm64-v8a/` | ~24 MB |
| 2 | `assets/toolchain/*` | `app/src/main/assets/toolchain/` | ~1056 MB |
| 3 | `assets/models/*` | `app/src/main/assets/models/` | ~63 MB |
| 4 | `assets/whisper/models/*` | `app/src/main/assets/whisper/models/` | 1.5 GB |
| 5 | `assets/proot/*` | `app/src/main/assets/proot/` | — |
| 6 | `assets/android_build/*` | `app/src/main/assets/android_build/` | ~399 MB |

After extracting, it writes `local.properties` with `sdk.dir=` (if it detects an
Android SDK).

### Three rules everything depends on

1. **It runs from any directory.** The script computes its own root
   (`$(dirname $0)/..`). Do not move it out of `tools/`.
2. **It is idempotent.** On a second run it skips what already exists with the correct
   size. If it was interrupted, **run it again** — do not delete anything by hand.
3. **`.so` files tracked by git are not touched.** `libptts_ffi.so` and
   `libptts_exec.so` come from the repo, not from the APK (otherwise they would be
   overwritten with an older version).

### If it fails

**`nu gasesc niciun APK in .../dist/` (no APK found)**
→ the APK is not in `dist/`. Check `ls dist/*.apk`. The name does not matter, the
extension does.

**`unzip lipseste` (unzip missing)**
```bash
sudo apt install unzip        # Debian/Ubuntu
brew install unzip            # macOS
```
On Windows: use **Git Bash** (ships with unzip) or WSL.

**`ATENTIE: assets/android_build lipseste din APK` (missing from APK)**
→ the APK comes from a build without build-tools. The app will start, but `build_apk`
(building APKs on the phone) will not work.

**It stops halfway, with no message**
→ disk space. `df -h .` — you need ~4 GB free during extraction.

---

## Step 3 — Build environment on the laptop

Here you build a **new** APK from your own sources. You need four components.

### 3.1 JDK 21

**JDK 17 or 21 required.** Gradle 8.11.1 does not work with JDK 8/11.

```bash
# Debian / Ubuntu
sudo apt install openjdk-21-jdk

# macOS
brew install openjdk@21

# Windows: download from https://adoptium.net (Temurin 21)
```

Verify:
```bash
java -version      # -> openjdk version "21.x"
```

> On Debian trixie **there is no openjdk-17** — use 21. AGP 8.7.3 works with it.

### 3.2 Android SDK (with build-tools and platform 36)

The simplest route — **Android Studio** (installs the SDK for you):
<https://developer.android.com/studio>

Or command-line tools only:
<https://developer.android.com/studio#command-tools>

You need:
- **platforms;android-36** (`compileSdk = 36`)
- **build-tools;35.0.1** (or 36.0.0)
- **platform-tools** (contains `adb`)

```bash
sdkmanager "platforms;android-36" "build-tools;35.0.1" "platform-tools"
```

> On Windows the SDK usually goes to `%LOCALAPPDATA%\Android\Sdk`.

### 3.3 NDK 29.0.14206865

The project pins `ndkVersion = "29.0.14206865"`.

```bash
sdkmanager "ndk;29.0.14206865"
```

> **Real trap, measured:** **NDK 27 gives SIGSEGV** when linking this project.
> Do not improvise with another version — install exactly 29.0.14206865.

### 3.4 Gradle — ships with the project

**Do not install Gradle.** The project has a wrapper: `./gradlew` (Gradle 8.11.1).
The first run downloads it automatically (~130 MB).

### 3.5 Tell Gradle where the SDK is

The file `local.properties` (in `workspace/app/net.sys32.agent/`) — it is not
committed, everyone has their own path:

```properties
sdk.dir=/home/USER/Android/Sdk
```

```properties
# Windows (note the double backslashes)
sdk.dir=C\:\\Users\\USER\\AppData\\Local\\Android\\Sdk
```

> `bootstrap_binaries.sh` writes it automatically if it finds the SDK. If it did not,
> write it by hand — otherwise Gradle reports **`SDK location not found`**.

### Full environment verification

```bash
cd android_agent/workspace/app/net.sys32.agent

export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64    # adjust to yours
export ANDROID_HOME=$HOME/Android/Sdk
export ANDROID_SDK_ROOT=$ANDROID_HOME

java -version                 # openjdk 21
./gradlew --version           # Gradle 8.11.1 + JVM 21
echo $ANDROID_HOME            # the SDK path
ls $ANDROID_HOME/platforms    # must contain android-36
ls $ANDROID_HOME/ndk          # must contain 29.0.14206865
```

If all four answer correctly, you are ready to build.

---

## Step 4 — Build the APK

```bash
cd android_agent/workspace/app/net.sys32.agent

export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
export ANDROID_HOME=$HOME/Android/Sdk
export ANDROID_SDK_ROOT=$ANDROID_HOME

./gradlew assembleDebug
```

**Result:** `app/build/outputs/apk/debug/app-debug.apk` (~2.4 GB)

### Real timings, measured on this project

- **first build** (downloads deps, compiles everything): **10-20 min**
- **incremental**, after a `.py` or `.kt` change: **20-40 s**
- **nothing changed** (`--offline`): **~14 s**
- **`clean assembleDebug`**: several minutes (re-packs 1.9 GB of assets)

### Useful commands

```bash
./gradlew --offline assembleDebug      # no network (deps in cache)
./gradlew clean assembleDebug          # rebuild from scratch
./gradlew assembleDebug --stacktrace   # when something breaks and you want details
```

### Relevant configuration (`app/build.gradle.kts`)

- `compileSdk 36`, `minSdk 26`, `targetSdk 36`
- `abiFilters arm64-v8a` (+ `x86_64` for the emulator)
- `packaging.jniLibs.useLegacyPackaging = true`
  → **mandatory**: otherwise the `.so` files cannot be executed on API 29+

### Verify the APK before installing

```bash
APK=app/build/outputs/apk/debug/app-debug.apk

ls -lh $APK                                             # 2863029937 bytes (2.86 GB, build 2026-11-02)
unzip -l $APK | grep -c 'assets/python/'                # ~1400 files
unzip -l $APK | grep 'assets/python/agent.py'           # the agent is present
unzip -l $APK | grep 'assets/toolchain/bin/clang'       # the toolchain is present
```

If `assets/toolchain/` is missing from the APK → bootstrap did not run or failed
partially. **Run `bash tools/bootstrap_binaries.sh` again** and rebuild.

### If it fails

**`SDK location not found`**
→ `local.properties` is missing or `sdk.dir` is wrong. See 3.5.

**`NDK not configured` / `SIGSEGV` at link time**
→ wrong NDK. It must be exactly `29.0.14206865` (3.3).

**`Unsupported class file major version`**
→ JDK too old. Needs 17 or 21.

**`OutOfMemoryError: Java heap space`**
→ in `gradle.properties`: `org.gradle.jvmargs=-Xmx3072m` (or more).

**The build takes over 40 min**
→ normal the first time if the network is slow; subsequent ones are in the order of
seconds.

---

## Step 5 — The phone: developer mode + USB debugging

Without this, the laptop cannot talk to the phone.

### 5.1 Enable Developer options

1. **Settings → About phone**
2. Find **Build number**
   - Samsung: *Settings → About phone → Software information → Build number*
   - Xiaomi/Redmi: *Settings → About phone → MIUI version* (tap 7 times)
   - Pixel/stock: *Settings → About phone → Build number*
3. **Tap Build number 7 times**
4. You see: *"You are now a developer!"*
5. If it asks for a PIN/password, enter it

### 5.2 Enable USB debugging

1. **Settings → System → Developer options**
   (Samsung: *Settings → Developer options*, directly in Settings)
2. Find **USB debugging** and turn it on
3. Confirm the dialog

### 5.3 Settings that help (recommended)

- **Stay awake** → ON. The screen will not sleep during the 2.4 GB transfer.
- **Verify apps over USB** → OFF (optional; can slow down installation)
- **Default USB configuration** → *File Transfer (MTP)*

> **Samsung:** *USB debugging* is enough. You do **not** need "OEM unlocking"
> (that one is for the bootloader, not for adb).

---

## Step 6 — Connection: adb + tcpip 5555

### 6.1 Verify adb on the laptop

`adb` ships with platform-tools (installed at 3.2).

```bash
adb version
```

If it is not in `PATH`, use the absolute path:
`$ANDROID_HOME/platform-tools/adb`

### 6.2 Connect over USB and authorize

1. **Data** USB cable (not charge-only — a frequent trap)
2. The phone shows: **"Allow USB debugging?"**
3. Tick **"Always allow from this computer"**
4. **Allow**

```bash
adb devices -l
# expected:
# RZGL102X5AT   device usb:1-1 product:a36xxx model:SM_A366B device:a36xxx
```

**`device`** = OK. **`unauthorized`** = you did not press Allow. **`offline`** = replug.

### 6.3 Open TCP port 5555

This is the step that lets you work **without the cable** afterwards:

```bash
adb tcpip 5555
# -> restarting in TCP mode port: 5555
```

The phone restarts in TCP mode. Find its IP on the network:

```bash
adb shell ip -f inet addr show wlan0 | grep inet
# -> inet 192.168.1.100/24 brd ... scope global wlan0
```

Or: *Settings → Connections → Wi-Fi → current network → IP address*

Connect over the network and **unplug the cable**:

```bash
adb connect 192.168.1.100:5555
# -> connected to 192.168.1.100:5555

adb devices          # the IP entry now appears too
```

The transfer now goes over Wi-Fi. For 2.4 GB, Wi-Fi 5 GHz is noticeably faster than
USB 2.0.

### 6.4 (Optional) Back to USB

TCP mode is lost on reboot. To return to USB:

```bash
adb usb
```

### Quick verification

```bash
adb shell getprop ro.product.model     # SM-A366B
adb shell getprop ro.build.version.sdk # 36
adb shell whoami                       # shell
```

> **Note:** in TCP mode, if the network changes (different router, VPN, hotspot),
> reconnect. The phone reverts to USB after every reboot — run `adb tcpip 5555` again.

---

## Step 7 — Installation

### Installation happens EXCLUSIVELY through ADB

**You cannot install this APK by tapping it on the screen. This is not a preference,
it is a hard technical limit.**

Two independent reasons, both insurmountable:

**1. Size — 2.4 GB (2,675,243,215 bytes).**

The Android system installer opens the APK, reads the manifest and copies it into
internal storage. For a 2.4 GB file, that process exceeds its memory and time budget
and stops with **"App not installed."** with no further detail. On modern Android, the
UI installer is designed for apps of tens or hundreds of MB, not for gigabytes.

**2. Location — Android 16 does not allow installing from `/sdcard`.**

Even if the file were small, it would still fail. Copy the APK into `Downloads`, tap
it, hit *Install* → the same generic message. The real reason, hidden by the UI:

```
System server has no access to read file context u:object_r:fuse:s0
Error: Can't open file: /sdcard/Download/app-debug.apk
Consider using a file under /data/local/tmp/
```

Android 16 blocks installing an APK from shared storage (SELinux context
`u:object_r:fuse:s0`). `/data/local/tmp` is readable by `system_server`, so it works.

**Conclusion:** `adb` is not a developer convenience. It is **the only way** the APK
gets installed on the phone.

---

### Option A — install over USB (the simplest)

```bash
# 1. send the APK to the phone
adb push app/build/outputs/apk/debug/app-debug.apk /data/local/tmp/agent.apk

# 2. install
adb shell pm install -r -g /data/local/tmp/agent.apk
# -> Success
```

Flags:
- `-r` — reinstall keeping data
- `-g` — grant all runtime permissions at once

**It takes 2-5 minutes** for 2.4 GB. Do not interrupt the transfer.

### Option B — install over Wi-Fi (no cable)

If you already did [Step 6](#step-6--connection-adb--tcpip-5555), `adb` works over the
network and you no longer need the cable:

```bash
adb connect 192.168.1.100:5555
adb devices                          # check: the IP entry appears, state "device"

adb push app/build/outputs/apk/debug/app-debug.apk /data/local/tmp/agent.apk
adb shell pm install -r -g /data/local/tmp/agent.apk
```

**Recommended on Wi-Fi 5 GHz** — for 2.4 GB the difference versus USB 2.0 is visible.
Downside: if the network drops mid-transfer, you start over.

### Option C — download directly on the phone (no laptop)

If you would rather not transfer 2.4 GB through adb, you can download the APK
**directly on the phone**. `curl` exists on the device, in `/system/bin/curl`.

```bash
# on the phone, in the app's terminal or from Termux:
curl -L -o /data/local/tmp/agent.apk https://sys32.net/dist/net.sys32.agent.apk

# the same integrity check as on the laptop:
sha256sum /data/local/tmp/agent.apk
# expected: f0872546b9d56c23d9478ec2222c7ec8f460f2543ddb28cc021d3fb197246a35

# then install:
pm install -r -g /data/local/tmp/agent.apk
```

From inside the app, the same thing through the ADB channel:

```python
import adb_client
adb_client.shared().shell('curl -L -o /data/local/tmp/agent.apk https://sys32.net/dist/net.sys32.agent.apk')
adb_client.shared().shell('pm install -r -g /data/local/tmp/agent.apk')
```

> **Why not directly into `Downloads`:** two reasons, both measured.
> (1) `pm install` refuses any path under `/sdcard` (SELinux context `fuse:s0`).
> (2) The app's own storage (`/data/data/net.sys32.agent/`) **is not readable even from
> a shell** — `ls` returns `Permission denied`, so `system_server` cannot open an APK
> from there.
>
> `/data/local/tmp` has the context `u:object_r:shell_data_file:s0` and is **the only
> place** from which `pm install` works. That is why all variants converge there.

### Option D — from inside the app (post-install)

Once the app is installed and ADB works, the agent itself can install APKs, including
itself: the `build_apk` tool has `action=install`, which moves the APK to
`/data/local/tmp` and runs `pm install` as `uid=2000`.

---

### What happens during installation

1. `pm install` copies the APK into the app's internal storage
2. **On first launch**, the app extracts ~1.5 GB from the APK (toolchain, Debian, models)
3. Only after extraction does the real footprint reach ~**4-5 GB** — hence the 8 GB
   free space requirement

Do not interrupt the installation and do not close the app on first start.

### Verification

```bash
adb shell dumpsys package net.sys32.agent | grep -E 'firstInstallTime|lastUpdateTime|versionName'
```

Clean install → `firstInstallTime == lastUpdateTime`.
If they differ, it is an upgrade over an older version.

### If it fails

**`INSTALL_FAILED_INSUFFICIENT_STORAGE`**
→ there really is no space. You need ~8 GB free (APK + extraction).

**`INSTALL_FAILED_UPDATE_INCOMPATIBLE`**
→ different signature than the installed version (other keystore).
```bash
adb uninstall net.sys32.agent     # WARNING: deletes app data
```
Then reinstall. If you want to keep data, use the same `debug.keystore` with which the
previously installed APK was signed.

**`device unauthorized`** after uninstall
→ the phone revokes the key. Press **Allow** again on the on-screen dialog.

**`adb: failed to read copy response`** during push
→ weak cable/USB port. Try another cable or use TCP (Step 6.3).

---

## Step 8 — First launch inside the app

```bash
adb shell am start -n net.sys32.agent/.MainActivity
```

Or tap the **AGENT** icon on screen.

### What happens, in order

**1. The setup panel** appears over the terminal:
- title `⚡ AGENT`, subtitle `First-time setup`
- message: `Please wait, take a coffee and relax...`
- a progress bar tied to granted permissions
- the `PERMISSIONS` list with live checkmarks

**2. The permission window (30 s).**
The app requests: Camera, Microphone, Location, Contacts, Photos & media,
Notifications, All files access.
**Grant all of them.** It closes as soon as they are all granted.

If you refuse any:
```
⚠ WARNING: 2 permission(s) not granted.
Setup CANNOT start until ALL are granted: Camera, Notifications
[ GRANT ALL PERMISSIONS ]
```
Setup is **mandatorily blocked**. If you chose "Don't ask again", the button opens the
app's Settings directly.

**3. The setup stages** appear once each, with a checkmark at the end:
```
✓ Environment     extracts the Python scripts + complete stdlib (~1.5 GB)
✓ Libraries       verifies the stdlib
✓ Bridge          starts AndroidBridge
✓ Agent           launches the Python process
```

**Extraction takes 3-10 minutes** on first launch. It is normal for the screen to
appear frozen. **Do not close the app.**

**4. The DeepSeek API key — MANDATORY.**

Without a key, the app starts and extracts its environment, but **the agent cannot
think**: you get no answer to any command.

If it is missing, the input appears:
```
paste DeepSeek key (sk-...) and send
```

Paste the key and send. It is saved locally, in `files/python/key.txt` and
`files/home/key.txt`. It goes nowhere else except the DeepSeek API.

Where to get the key: <https://platform.deepseek.com> → *API keys* → *Create*.
It looks like `sk-...` (35 characters).

> **Security note:** do not put the key in git, in the APK or in `assets/`. It is
> written only at runtime, into the app's private storage. The `key.txt` file is
> already in `.gitignore` for exactly this reason.

**5. The terminal appears** once all stages are checked.

### ADB — mandatory, verify now

If ADB is not running, the app works, but the privileged tools (`android`, `adbsh`,
`build_apk`, `binder`) have nothing to work with. Check right after setup:

```bash
adb shell pm list packages | grep sys32     # from the laptop -> must answer
```

From the app's terminal, the first sign that ADB works:

```python
import adb_client
adb_client.shared().shell('id -u')     # -> 2000
```

If you get `not authorised` or a timeout, see
[Step 6](#step-6--connection-adb--tcpip-5555): `adb tcpip 5555` must be run on the
phone, and the *Allow USB debugging?* dialog accepted.

### Verification

```bash
adb shell ps -A -o PID,PPID,NAME | grep -E 'sys32|libpyexec'
# you should see the Python process (libpyexec) among the results
```

---

## Final verification

Everything works if **all** of these answer correctly:

```bash
# 1. the app is installed
adb shell pm list packages | grep sys32
# -> package:net.sys32.agent

# 2. the Python process is running
adb shell ps -A | grep libpyexec

# 3. the assets were extracted
adb shell run-as net.sys32.agent ls files/python/agent.py
adb shell run-as net.sys32.agent ls files/pyhome/.stdlib_ok

# 4. the servers answer (from the app's terminal)
cat /data/data/net.sys32.agent/files/bridge.port    # AndroidBridge port (always, after setup)
cat /data/data/net.sys32.agent/files/dshell.port    # DShell port (appears when the agent starts)

# 5. the toolchain is functional (from the app's terminal)
toolchain selftest        # -> ok for C, C++, Python ext
```

---

## Quick troubleshooting

**The app starts and closes immediately**
-> Logcat: `adb logcat -d | grep -iE 'sys32|AndroidRuntime|FATAL' | tail -40`
The most common cause on a clean install: the Python stdlib did not extract fully.

**Setup hangs at "Environment"**
-> `adb shell run-as net.sys32.agent du -sh files/pyhome`
If it is under ~400 MB, extraction is still running or failed (space). Check `df /data`.

**The terminal does not open / Debian does not start**
-> Normal on first tap: the rootfs is extracted step by step, with progress.
It takes a few minutes. The final message is `READY !`.

**`adb` does not see the phone at all**
-> `adb devices` empty: charge-only cable? Another cable. Another USB port (prefer the
rear ports on a desktop). On Windows: install the manufacturer's USB driver.
On Linux: `sudo usermod -aG plugdev $USER` then re-login.

**`adb connect` returns `Connection refused`**
-> TCP mode is lost on reboot. Reconnect USB and run `adb tcpip 5555` again.
Also check that laptop and phone are on the **same** network (no VPN, no separate
hotspot).

**The build succeeds, but the app has no toolchain (`build_apk` fails)**
-> `assets/toolchain/` is missing from the APK. Run `bash tools/bootstrap_binaries.sh`
again, then rebuild. Verify: `unzip -l app-debug.apk | grep -c 'assets/toolchain/'`.

---

## Recap in a single window

```bash
# --- on the laptop ---
git clone https://github.com/fetidness/android_agent.git && cd android_agent
mkdir -p dist
curl -L -C - -o dist/net.sys32.agent.apk https://sys32.net/dist/net.sys32.agent.apk
sha256sum dist/net.sys32.agent.apk                    # f0872546...246a35
bash tools/bootstrap_binaries.sh                      # extracts the binaries from the APK

cd workspace/app/net.sys32.agent
export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
export ANDROID_HOME=$HOME/Android/Sdk
./gradlew assembleDebug                               # ~10-20 min the first time

# --- on the phone ---
# Settings > About phone > Build number x7 > Developer options > USB debugging ON
# connect USB, press Allow on the phone

adb tcpip 5555                                        # open the port
adb connect 192.168.1.100:5555                        # optional: no cable

# --- installation ---
adb push app/build/outputs/apk/debug/app-debug.apk /data/local/tmp/agent.apk
adb shell pm install -r -g /data/local/tmp/agent.apk  # -> Success
adb shell am start -n net.sys32.agent/.MainActivity

# --- inside the app ---
# grant ALL permissions -> wait for extraction (3-10 min) -> paste the API key
```

---

*Document compiled from the commands and values found in the repo:
`tools/bootstrap_binaries.sh`, `app/build.gradle.kts` (AGP 8.7.3, Gradle 8.11.1,
compileSdk 36, NDK 29.0.14206865), `AndroidManifest.xml`, and behaviour measured on a
Samsung SM-A366B running Android 16.*
