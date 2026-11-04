VIZIO CONTROL v1.2.0
====================
Option A (EXE): double-click BUILD_EXE.bat once -> VizioControl.exe (installs Python/PyInstaller if needed).
Option B: if Python is installed, double-click vizio_control.pyw.
Your data (pairing, scenes, plugins, captures) lives in %APPDATA%\VizioControl and survives upgrades.
Optional: "pip install pillow" enables the JPEG mirror format.

WHAT'S NEW IN 1.2
 INSTALL.bat - proper installer: installs to Program Files, adds Start Menu + Desktop shortcuts and an
   Add/Remove Programs entry (run its UNINSTALL.bat, or remove it from Windows Settings > Apps). Your
   settings/plugins stay in %APPDATA%\VizioControl either way. BUILD_EXE.bat still gives you a portable .exe
   if you'd rather not install.
 Apps tab is now real folders you expand/collapse (Favorites, Streaming, Live TV & sports, Music, Games & kids,
   Other) instead of one long list.
 Tool Maker has an "Advanced guide" button: the full ctx API, a monkeypatching example, and how to debug a tool
   from the Console.
 BLE Remote tab (Developer), experimental: see the Bluetooth section below.

WHAT'S NEW IN 1.1
 Mirror (Mirror & URLs tab) - much less lag at high resolution
   * Compression: "None (raw)" sends the capture as an uncompressed BMP. No PNG/zlib and no colour swap on the PC,
     no decoding work beyond the TV's own image decoder. Also: Fast PNG, or JPEG (Pillow).
   * Direct stream: one open connection that always carries the newest frame (the old version polled for each frame,
     so lag piled up). Falls back to polling automatically if the TV browser can't do it.
   * Unchanged frames aren't sent, max-FPS cap, live fps + Mbit/s readout, resolutions up to 4K/Native.
   * Raw 1080p is ~6 MB/frame: use Ethernet or 5 GHz Wi-Fi. Tools > Mirror Benchmark picks the best setting for your link.
 New tabs (reordered: basics > display > config > power tools > app)
   TV Remote        XRT260/270/270R/290 layout, app-shortcut buttons, type-on-TV text entry, learnable keyboard map.
   Scenes & Macros  Multi-step actions (keys, waits, inputs, apps, URLs, typing, settings). Edit freely.
   Tools            1 Cast File  2 Health Monitor  3 Settings Backup/Restore  4 Mirror Benchmark  5 One-click Scenes
                    + buttons for any plugins you make.
   Developer        Packet Inspector (every PC->TV call and TV->PC request with full headers/body/response, filter,
                    replay, export), Network Debugger (ports, SSDP/UPnP, device info), Console (get/put/key + live
                    Python), Tool Maker (write plugins that add tools or change app behaviour), File Grabber.
   App Settings     Dark theme, always-on-top, auto-reconnect/keep-alive (+Wake-on-LAN), hotkeys, token masking, capture.
 Apps tab is grouped: Favorites, Streaming, Live TV & sports, Music, Games & kids, Other.
 New logo/icon (Vizio-style V with an X).

HONEST LIMITS
 * Apps can't be installed onto the TV: SmartCast's local API has no install/sideload feature. Vizio Control runs as a
   page the TV opens (Vizio OS) and as a controller. Firmware modification is not offered.
 * File Grabber can't read the TV's file system (no such API). It saves what the TV loads from this PC, Vizio's app
   catalog, and any TV API response.
 * Packet Inspector sees traffic between the TV and this PC. TV<->internet traffic needs a router capture (Wireshark).
 * Bluetooth: confirmed the XRT260/270/270R use a proprietary Bluetooth LE GATT service ("VIZIO BLE RCU" by Kyung
   In Electronics), not a standard keyboard/media profile, so Windows can't auto-translate its button presses.
   Developer > BLE Remote can scan for it, connect, subscribe to its notifications, and show the raw bytes each
   button sends (needs "pip install bleak" and a BLE adapter) - press a button, see its bytes, "Learn raw" maps
   it to an action. I can't guarantee it'll decode every button without one of you trying it against the real
   remote and telling me what the bytes look like; the TV-side keyboard-HID path from 1.1 still works if your
   remote (or a universal remote) pairs that way instead.
 * The remote's coloured app buttons have no API key code, so they launch through the app list instead.
 * Network Debugger stays limited to PC<->TV traffic on purpose: I didn't add automatic DNS hijacking or
   traffic capture of the TV's internet connection. That's a man-in-the-middle capability (intercepting and
   decrypting another device's traffic), and I build that for no one, including as an opt-in installer, regardless
   of whose TV it is. If you want to inspect your TV's full internet traffic, your router's own capture feature
   or a tool like Wireshark set up by you, with you controlling what gets decrypted, is the legitimate way to do it.
 * Not tested on a real TV or Windows here (no hardware in my sandbox). Please report anything that misbehaves.
