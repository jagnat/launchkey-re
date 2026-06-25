# 03 — Obtaining the firmware (without opening the case)

Goal: get the actual firmware image. We chose the **lowest-risk** route: download
it from Novation's own update servers, exactly like their updater does.

## The reasoning chain (this is the transferable skill)
Novation updates firmware through a web app, **Novation Components**
(`components.novationmusic.com`). A web app that flashes your device must, at some
point, **fetch the firmware over HTTPS**. So if we watch where it fetches from, we
get the file. We never needed a packet sniffer — the app's own JavaScript tells us.

### Step 1 — the SPA config
`components.novationmusic.com` is an Ember single-page app. These embed their
runtime config in a `<meta name="...config/environment">` tag (URL-encoded JSON).
Decoding it gave:
```
APP.API_HOST = "https://components.novationmusic.com"
```
and pointed at the JS bundle `/assets/main-<hash>.js`.

### Step 2 — read the app bundle
We downloaded the (minified) bundle and grepped for `firmware`. Two findings:
- firmware is downloaded from a constant `IT`, where
  `IT = `${API_HOST}/api/v2/firmwares``
- the list endpoint returns `{ firmwares: [ {id, product, build, version, url}, ... ] }`
- an individual file is fetched from `` `${IT}/${id}/file` ``

> Lesson: minified JS keeps **string literals** intact. `grep`-ing a bundle for
> domain names, paths, and keywords (`firmware`, `api`, `.json`) is one of the
> fastest ways to map a web API.

### Step 3 — hit the API
`GET https://components.novationmusic.com/api/v2/firmwares` → JSON, **no auth**,
118 firmwares for all Novation products. Filtered for `launchkey-mini-mk3`:

| build | version | id | file |
|---|---|---|---|
| 254 | 1.0   | 18 | /api/v2/firmwares/18/file |
| 255 | 1.0.1 | 19 | … |
| 258 | 1.0.2 | 20 | … |
| 259 | 1.0.3 | 23 | … |
| 270 | 1.0.4 | 69 | … |
| 303 | 1.1   | 87 | … |
| 417 | 1.1.1 | 128 | … |
| 425 | 1.1.2 | 149 | … |
| 461 | 1.2   | 159 | /api/v2/firmwares/159/file |

We downloaded **159 (v1.2)** to analyse and **149 (v1.1.2)** because that's what
*your* unit runs (handy for a later diff). Files land in `firmware/`.

## Matching the version your device reported
The MIDI identity reply gave version bytes `00 04 02 05` (see note 02). Components'
own code decodes these as: reverse the 4 bytes, then `Σ byteₙ·10ⁿ`:
```
[00 04 02 05] -> reversed [05 02 04 00] -> 5 + 2·10 + 4·100 + 0·1000 = 425
```
425 == build 425 == v1.1.2. So the firmware-version "number" you see in apps is
literally these 4 bytes read as decimal digits.

## Why this route first (vs. the alternatives)
- **Sniff a live update**: teaches the bootloader handshake but needs a pending
  update and USB-MIDI capture. We'll still do this later to learn the *protocol*.
- **Hardware SWD dump**: the only way to get the **bootloader** + real flash state,
  but requires opening the case and may be blocked by readout protection (RDP).
- **Server download (this)**: zero risk, gets the exact application image in
  minutes. Doesn't include the bootloader (first 32 KB) — that's the one gap.

## Reproduce
```
curl -s https://components.novationmusic.com/api/v2/firmwares -o firmware/firmwares-api.json
curl -sL https://components.novationmusic.com/api/v2/firmwares/159/file \
     -o firmware/launchkey-mini-mk3_v1.2-build461.syx
```
