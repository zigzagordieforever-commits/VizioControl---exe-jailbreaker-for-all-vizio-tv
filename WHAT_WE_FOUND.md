# What we found while testing VizioControl

These notes mix things tested on one VIZIO TV, details from public SmartCast research, and things that still need testing. A result on one TV does not guarantee the same result on every model or firmware.

## Tested on one TV

The main test TV was a VIZIO V505-J09 running SmartCast firmware `1.720.9.1-1` (software string reported as `1.720.9.1-1.2.1`). These are observations from that setup, not a promise of support for every V505-J09.

- The TV answered a ping on the local network.
- HTTPS SmartCast API requests to port `7345` worked. Plain HTTP did not behave the same way.
- `GET /state/device/deviceinfo` returned a successful JSON response in the test setup without an AUTH token.
- A Conjure URL hosted by the PC launched on the TV.
- The TV loaded the PC's screen-mirroring page and showed the changing desktop picture. The mouse pointer was initially missing; the current source has a separate cursor-overlay implementation that still needs testing across PCs and TVs.
- Some other API actions can still require PIN pairing even when the URL launch and device-info request work.

## SmartCast API basics from community research

- Port `7345` is used by many newer SmartCast models; older firmware may use port `9000`.
- The local API uses HTTPS. A self-signed or TV-specific certificate can make normal certificate checks fail.
- The API is not perfectly REST-like. Check the JSON `STATUS.RESULT` field as well as the HTTP status.
- Pairing uses a short PIN challenge and returns an AUTH token. Treat that token like a password.
- The Conjure URL launch used by this project sends app ID `17`, namespace `4`, and the page URL in the `MESSAGE` field. This is based on public community implementations and was also observed working in the test setup.

## Community projects and useful links

These are other projects and docs that helped explain the protocol. They are not part of VizioControl, and their maintainers can change them at any time.

1. **get-air/vizio** — https://github.com/get-air/vizio
   - A newer SmartCast client with examples for PIN pairing, AUTH token use, remote control, app launch, and Conjure URL launch.
   - Its notes explain that launching a Conjure page is not the same as installing a permanent home-screen app.

2. **pyvizio** — https://github.com/raman325/pyvizio
   - A Python SmartCast client with examples for app lists, remote commands, and app launch configurations.
   - The project says it is in maintenance mode and points people toward `vizaio`.

3. **vizaio** — https://github.com/raman325/vizaio
   - A newer async Python SmartCast client and CLI. Useful for comparing current pairing and API behavior.

4. **Vizio SmartCast API notes (exiva)** — https://github.com/exiva/Vizio_SmartCast_API
   - Community notes about HTTPS, ports, common API routes, and app launch values. Some of the documentation is old, so verify details on the actual TV.

5. **VIZIO Content Partners** — https://www.vizio.com/en/content-partners
   - VIZIO's official page for bringing an app or channel to its platform. This is the right place to start for authorized public app distribution.

6. **TV Labs SmartCast docs** — https://docs.tvlabs.ai/platform/platforms/smartcast
   - Professional testing documentation about app development, test connections, and debugging. Their tools and device access may be required; this is not proof that every consumer TV supports general ZIP sideloading.

7. **BlackBox QA Vizio installation notes** — https://www.blackboxqa.ca/vizio-installation
   - Describes a partner/test workflow that uses whitelisting and a Conjure launcher. Treat this as a test-provider process, not a universal consumer install method.

8. **SmartCast security research** — https://github.com/vindeckyy/smartcast-backdoor
   - A security write-up about risks around privileged web views on certain tested firmware. It is included as a security-awareness link only. VizioControl does not use or reproduce its exploit techniques. Do not try security tests on TVs you do not own or have permission to test.

## Ads and DNS notes

- DNS logs can show which domain names a TV asks to resolve and which record types it requests.
- DNS logs do not show the full HTTPS page, video stream, account data, or exact ad content.
- Some observed hostnames looked related to advertising or measurement, but a hostname alone does not prove every ad path.
- Blocking a domain can break normal app loading, pictures, sign-in, or playback. Keep core VIZIO, Netflix, connectivity-check, and time services working unless you know exactly what a rule does.
- DNS does not push app files to the TV. It only answers name lookups.

## App installation reality

The current App Maker exports web app files and can launch a page that the TV can reach. It does not create a signed native SmartCast package or install a permanent launcher tile. VIZIO's official partner process is the documented public route for platform distribution. Some testing companies describe whitelisted developer workflows, but those are not a general consumer sideload feature.

## What still needs testing

- Pairing on more VIZIO model/firmware combinations.
- Whether saved AUTH tokens remain valid after a TV restart or factory reset.
- Screen mirror speed and cursor accuracy at different display sizes.
- Audio capture and playback on different Windows sound devices.
- App Maker keyboard/remote navigation on different TV browsers.
- DNS proxy stability and firewall behavior on different Windows PCs.
- EXE launch and antivirus behavior on clean Windows 10 and Windows 11 machines.
