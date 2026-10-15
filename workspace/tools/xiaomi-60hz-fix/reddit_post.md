# Reddit post draft — r/Xiaomi (also fits r/AndroidQuestions, r/HyperOS, r/Redmi)

**Title:**
MIUI/HyperOS keeps reverting my 120Hz to 60Hz — found the hidden setting that causes it (permanent fix, no root)

**Body:**

Every guide says "just set 120Hz in Settings". I did that. Ten seconds later it dropped back to 60Hz, while the menu still said 120. Rebooted, same thing. Screen is fine, it's not the app I was using, it's not something I did.

Turns out there's a **second** refresh rate setting that MIUI hides from you.

---

### The cause

Stock Android controls refresh rate with one setting: `peak_refresh_rate`. MIUI/HyperOS has a second one that takes priority:

```
miui_refresh_rate
```

When the two disagree, MIUI follows the hidden one. So you set 120 everywhere you can see, while the hidden value sits at 60.

And something keeps rewriting that hidden value on a timer: `com.miui.powerkeeper`, Xiaomi's battery service. Its literal job is to toggle 60 <-> 120 to save battery.

You can watch it happen:

```
# Linux / macOS
adb shell dumpsys settings | grep miui_refresh_rate

# Windows (cmd)
adb shell dumpsys settings | findstr miui_refresh_rate

# Windows (PowerShell)
adb shell dumpsys settings | Select-String miui_refresh_rate
```

Mine looked like this:

```
16:08:27  value:120  packageName:com.miui.powerkeeper
16:08:37  value:60   packageName:com.miui.powerkeeper   <-- reverts
16:08:43  value:120  packageName:com.miui.powerkeeper
16:08:44  value:60   packageName:com.miui.powerkeeper   <-- reverts again
```

---

### Platform note (read once)

Every command here is identical on Windows, Linux and macOS **except the text filter**, which runs on your PC, not on the phone:

|  | filter command |
|---|---|
| Linux / macOS | `grep` |
| Windows (cmd) | `findstr` |
| Windows (PowerShell) | `Select-String` |

The `adb shell ...` part never changes. Below, each filtered command is shown for the platform you use.

---

### Step 1 — Diagnose (30 seconds, needs ADB)

**a) What mode is active right now** — you want `120.00 Hz`, not `60.00 Hz`

```
# Linux / macOS
adb shell dumpsys SurfaceFlinger | grep peak-refresh

# Windows
adb shell dumpsys SurfaceFlinger | findstr peak-refresh
```

**b) Does your panel actually support 120Hz**

```
# Linux / macOS
adb shell dumpsys display | grep supportedRefreshRates

# Windows
adb shell dumpsys display | findstr supportedRefreshRates
```

You want something like `[60.0, 120.0, 90.0]`. If `120.0` is absent, the hardware can't do it — stop here.

**c) Read both refresh settings** (no filter needed, same on all platforms)

```
adb shell settings get system peak_refresh_rate
adb shell settings get secure miui_refresh_rate
adb shell settings get system miui_refresh_rate
```

If `peak_refresh_rate` is `120` but `miui_refresh_rate` is `60` or `null`, you found the mismatch.

**d) Catch the culprit**

```
# Linux / macOS
adb shell dumpsys settings | grep miui_refresh_rate

# Windows
adb shell dumpsys settings | findstr miui_refresh_rate
```

If you see `packageName:com.miui.powerkeeper` writing `value:60`, that's your saboteur.

---

### Things that DON'T work

- `am force-stop com.miui.powerkeeper` — the service restarts within seconds.
- `pm disable-user com.miui.powerkeeper` — `SecurityException: Cannot disable system packages` on Android 14/15/16.
- `appops set ... WRITE_SETTINGS deny` — not respected; the service is restarted.

---

### Step 2 — The permanent fix

Uninstall the battery service **for the current user**: no root, doesn't touch the system partition, reversible at any time.

```
adb shell pm uninstall --user 0 com.miui.powerkeeper
```

You want the single word: `Success`.

Confirm it is gone:

```
adb shell pm path com.miui.powerkeeper

# Linux / macOS
adb shell ps -A | grep powerkeeper

# Windows
adb shell ps -A | findstr powerkeeper
```

Both should return nothing.

Now force 120Hz in every namespace (same on all platforms):

```
adb shell settings put system peak_refresh_rate 120
adb shell settings put system min_refresh_rate 120
adb shell settings put secure miui_refresh_rate 120
adb shell settings put system miui_refresh_rate 120
```

---

### Step 3 — Verify

Wait a full minute, then:

```
# Linux / macOS
adb shell dumpsys SurfaceFlinger | grep peak-refresh

# Windows
adb shell dumpsys SurfaceFlinger | findstr peak-refresh

adb shell settings get secure miui_refresh_rate
```

Expected: `120.00 Hz` and it does not drop; `miui_refresh_rate` stays `120`.

Then reboot and check again — same three commands after the phone boots:

```
adb reboot
```

If it still reads 120Hz, the fix is permanent.

---

### Revert (back to Xiaomi's adaptive behaviour)

```
adb shell pm install-existing com.miui.powerkeeper
adb shell settings put secure miui_refresh_rate 60
```

Note: constant 120Hz uses more battery than adaptive switching.

---

### Warnings

Only remove this one battery service. **Never** uninstall `com.android.systemui`, `com.android.settings`, `com.android.vending` (Play Store), `com.google.android.gms`, or any `com.android.providers.*` package — you can end up with a phone that won't boot, recoverable only by reflashing the firmware.

`pm uninstall --user 0` is reversible with `pm install-existing <package>`, but only if you remember the package name. Keep notes.

---

### ADB setup (one time)

1. On the phone: **Settings → About phone**, tap **MIUI/HyperOS version** 7 times to unlock **Developer options**.
2. In **Developer options**, enable **USB debugging**.
3. On the PC, install Platform Tools (Google's Android developer site = a zip on Windows):
   - **Windows:** unzip it and open cmd or PowerShell in that folder (or add the folder to PATH).
   - **macOS:** `brew install android-platform-tools`
   - **Linux (Debian/Ubuntu):** `sudo apt install adb`
4. Connect the phone with a **data** cable (not charge-only) and run `adb devices`.
5. Approve the dialog on the phone, ticking **Always allow from this computer**.

---

### Tested on

Redmi 2409FPCC4G, Android 16 / HyperOS, MediaTek. The mechanism (hidden `miui_refresh_rate` reverted by `com.miui.powerkeeper`) shows up across recent MIUI/HyperOS builds, but exact names can vary by region and version — run the diagnostic first so you react to what *your* device is doing.
