# Release candidate testing checklist

Run these checks before calling a build stable. Not every item can be tested without a real TV.

## Source and build
- [ ] `python -m py_compile vizio_control.pyw`
- [ ] `python -m unittest discover -s tests -v`
- [ ] Run `BUILD_EXE.bat` on a clean Windows 10/11 PC.
- [ ] Confirm `Release Candidate` contains only `VizioControl.exe` after a successful build.
- [ ] Start the EXE and close it normally.
- [ ] Confirm profiles are saved under `%APPDATA%\VizioControl`.

## TV connection
- [ ] TV and PC are on the same private LAN.
- [ ] Connect to the correct TV IP.
- [ ] Read device information.
- [ ] Test a read-only request.
- [ ] Pair using the PIN shown on the TV.
- [ ] Retry a request that previously required pairing.
- [ ] Confirm the AUTH token is masked in the UI/logs.

## TV page and screen mirror
- [ ] Launch the hosted TV page.
- [ ] Start screen mirroring.
- [ ] Check that the picture updates.
- [ ] Check that the cursor appears and follows the PC pointer.
- [ ] Try a different monitor resolution / scaling mode.
- [ ] Close the app and confirm the local web server stops.

## App Maker
- [ ] Create a project from each starter template.
- [ ] Preview the page on the PC.
- [ ] Launch the page on the TV.
- [ ] Navigate with TV arrows and OK.
- [ ] Export the project ZIP and open its HTML on a PC.
- [ ] Confirm docs do not claim the ZIP installs a native TV app.

## Network tools
- [ ] Test DNS Sender against a known resolver.
- [ ] Test DNS proxy only on a trusted LAN.
- [ ] Stop DNS proxy and confirm it releases port 53.
- [ ] Confirm the PC's own DNS settings were not changed automatically.

## Privacy and safety
- [ ] Check that no AUTH token or profile file is included in the GitHub ZIP.
- [ ] Check that logs/screenshots have been redacted.
- [ ] Confirm no router settings are changed automatically.
- [ ] Confirm no unknown PUT/POST requests are sent automatically.
