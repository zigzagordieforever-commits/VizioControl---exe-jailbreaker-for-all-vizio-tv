# Install and build VizioControl

This page is written so you can follow it without knowing how Python works.

## Option 1 — use the EXE (easiest)

1. Open the project's GitHub page.
2. Click **Releases**.
3. Download `VizioControl.exe` from the newest release.
4. Save it somewhere you can find it, such as your Desktop or Documents.
5. Double-click it to open VizioControl.

Windows SmartScreen may show a warning because the EXE is not signed by a big software publisher. Only run it if you trust the source you downloaded it from. Do not turn off Windows security for random downloads.

## Option 2 — run the Python source

1. Install Python 3.12 or a newer compatible Python 3 version from https://www.python.org/downloads/windows/.
2. During setup, enable **Add Python to PATH**.
3. Extract the full project ZIP.
4. Open the extracted folder.
5. Double-click `SETUP_DEPENDENCIES.bat` and let it finish.
6. Double-click `vizio_control.pyw`.

If Windows says Python is missing, restart the terminal or sign out and back in, then try again.

## Build your own EXE on Windows

You need Windows 10/11, Python 3, an internet connection for the build dependencies, and the full project folder.

1. Extract the full GitHub ZIP. Do not try to build from inside the ZIP preview.
2. Double-click `BUILD_EXE.bat`.
3. Wait for the build to finish. The first build can take a while because it downloads the build tools.
4. Open the folder named `Release Candidate`.
5. The finished file should be `VizioControl.exe`.
6. Test that EXE before sharing it.

### What the build script cleans up

After PyInstaller succeeds and the EXE has been copied, the script removes its temporary `.build_tmp` folder and temporary Python cache files. It also clears other old files from `Release Candidate`, leaving only the new `VizioControl.exe` there.

It does **not** delete the source code, README, docs, tests, icon, or batch files. Those files are needed to keep the GitHub project buildable. The EXE is a separate release output.

If the build fails, the script keeps the old EXE (if there was one) and shows an error. Check the messages before trying again.

## First TV connection

1. Connect the TV and PC to the same home network.
2. Find the TV's IP address in the TV network settings.
3. Open VizioControl and add/select the TV.
4. If a request says pairing is required, open **Advanced / Developer → SmartCast Sender → Pair TV / Fix 403**.
5. Approve the pairing prompt on the TV and enter its four-digit PIN in VizioControl.
6. Retry the action.

Do not change router settings just to use the basic SmartCast connection. Windows Firewall may ask whether to allow VizioControl on a private network; only allow it on a network you trust.

## Run as administrator?

Do not run everything as administrator by default. Try the normal app first. Use `RUN_AS_ADMIN.bat` only if you need a feature that requires elevated permission, such as binding a local DNS listener to port 53 or a capture feature that Windows blocks.

## If it does not open

- Make sure the ZIP was fully extracted.
- Try the Python source version to see whether Windows shows a useful error.
- Check that Windows Defender did not quarantine the EXE.
- Run `python -m py_compile vizio_control.pyw` from the project folder to check the source syntax.
- Read [Troubleshooting](docs/TROUBLESHOOTING.md).
- If you open a GitHub issue, never attach `profiles.json` or an AUTH token.
