# VizioControl 1.7.2-rc1 — Release Candidate

VizioControl is a Windows app for working with VIZIO SmartCast TVs on your home network. It has TV controls, screen mirroring, network tools, a SmartCast request tester, and an App Maker for TV-friendly web pages.

This is a **release candidate**, which means it is ready for people to test, but it still needs more testing on different TVs and Windows PCs. Please report bugs with the steps to reproduce them.

> **Not made by or connected to VIZIO.** VIZIO and SmartCast are trademarks of their owners.

## Quick install

1. Download the project ZIP from the GitHub release or click **Code → Download ZIP**.
2. Extract the whole ZIP to a normal folder, like `Documents\VizioControl`.
3. Double-click `SETUP_DEPENDENCIES.bat` if you want to run the Python version.
4. Double-click `vizio_control.pyw` to start it. If Windows blocks a feature that needs admin permission, close it and use `RUN_AS_ADMIN.bat` only when needed.

Most people should use the ready-made `VizioControl.exe` from the GitHub **Releases** page. It does not need Python installed. See [Build and install](BUILD_AND_INSTALL.md).

## What it can do

- Find and connect to supported VIZIO TVs on the same local network.
- Send remote-control commands and read TV information.
- Pair with a TV using the PIN shown on the TV, then use the returned AUTH token for commands that need it.
- Launch a hosted web page on the TV through the SmartCast Conjure path.
- Mirror the Windows screen to the TV and show a separate mouse pointer overlay.
- Make simple TV-friendly web apps with the App Maker, preview them, launch them, and export their web files.
- Inspect SmartCast requests and test DNS/network behavior.

Some features depend on the TV model, firmware, Windows drivers, firewall rules, and whether the TV is paired.

## Important: web app is not the same as a native TV app

The App Maker creates web apps. Conjure can open a page hosted on your PC, but the TV must be able to reach that page. If the page is hosted by VizioControl on your PC, the PC has to stay on and connected while the TV uses it.

Exporting a web-app ZIP does **not** install a permanent native SmartCast app. Permanent distribution on VIZIO's platform goes through VIZIO's partner process. Do not advertise the exported ZIP as a native TV installer.

## Pairing and HTTP 403

Some SmartCast API requests work without pairing and others return `HTTP 403` or `REQUIRES_PAIRING`. Open **Advanced / Developer → SmartCast Sender → Pair TV / Fix 403**, approve the pairing prompt on the TV, and enter the PIN shown on the TV. The app saves the AUTH token in its local profile so it can reuse it.

**Keep the profile private.** The current app stores TV profile data, including the AUTH token, in `%APPDATA%\VizioControl\profiles.json`. Do not post that file, screenshots of the token, or raw logs containing credentials.

## Things we learned

- Recent SmartCast TVs commonly expose the local API over HTTPS on port `7345`; older models may use `9000`.
- The API can return an empty reply over plain HTTP while HTTPS works.
- A TV can load a Conjure URL hosted by a PC on the same LAN. The TV needs network access to that URL.
- DNS logs show hostnames and record types. They do not show the contents of encrypted HTTPS traffic and do not install apps.
- Pairing is a separate step from launching a Conjure page. A page launch working does not mean every API command is authorized.
- A closed port `9555` does not mean VizioControl can turn on developer mode. Developer access can depend on VIZIO approval/whitelisting.
- Screen mirroring and the separate cursor overlay are different parts of the feature; report if the pointer is missing or out of sync.

More notes and links are in [What we found](docs/WHAT_WE_FOUND.md).

## Safety notes

- Use this on your own TV and trusted home network.
- Do not port-forward SmartCast ports to the internet.
- Do not point your PC's DNS at VizioControl's DNS listener; that can cause a DNS loop.
- Do not expose the DNS forwarder to the public internet.
- Only send API writes you understand. Unknown PUT/POST requests can change TV settings.
- The TV uses a local/self-signed TLS certificate. The app relaxes certificate checks for its TV connection; keep that connection on your trusted LAN.
- Only install plugins you trust. Plugins are Python files and can run code on your PC.

## Report a bug

Open **Issues** on GitHub and use the bug report template. Include your Windows version, TV model/firmware, the exact steps, and the full error text. Hide your TV's serial number, AUTH token, Wi-Fi password, and public IP address.

## Project files

- `vizio_control.pyw` — main app source code.
- `BUILD_EXE.bat` — builds a single Windows EXE and cleans up temporary build files.
- `Release Candidate/` — the build output folder. After a successful build it contains only `VizioControl.exe`.
- `BUILD_AND_INSTALL.md` — simple install and build steps.
- `docs/` — findings, known limits, testing notes, and compatibility notes.
- `tests/` — basic automated source checks.

## Current test status

The source compiles and the repository includes automated smoke checks. The release candidate has **not** been fully tested on every Windows version or VIZIO model. A successful build does not prove every TV feature works. Please test carefully and report what works on your model.

## Thanks

This project learned from public SmartCast documentation and community projects. See the links in [What we found](docs/WHAT_WE_FOUND.md). Please check each project's own license before copying code from it.
