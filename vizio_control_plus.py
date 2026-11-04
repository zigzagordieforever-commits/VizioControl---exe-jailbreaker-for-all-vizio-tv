import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request
from tkinter import messagebox, ttk
import tkinter as tk

APP_NAME = "VizioControl"
APP_VERSION = "2.0.0"
REPO_OWNER = "zigzagordieforever-commits"
REPO_NAME = "VizioControl---exe-jailbreaker-for-all-vizio-tv"
GITHUB_RELEASE_URL = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/latest"


FEATURES = [
    {
        "name": "Pair TV",
        "category": "Connect",
        "mode": "Quick",
        "level": "Basic",
        "description": "Pair and connect to a Vizio SmartCast TV over the same local network.",
        "action": "pair",
    },
    {
        "name": "Scan Network",
        "category": "Connect",
        "mode": "Quick",
        "level": "Basic",
        "description": "Find available smart TVs quickly and choose the best match.",
        "action": "scan",
    },
    {
        "name": "Remote Pad",
        "category": "Remote",
        "mode": "Quick",
        "level": "Basic",
        "description": "Use the desktop keyboard and mouse to act as a TV remote.",
        "action": "remote",
    },
    {
        "name": "App Launch Catalog",
        "category": "Apps",
        "mode": "Advanced",
        "level": "Standard",
        "description": "Launch known apps and group them by category for easier browsing.",
        "action": "apps",
    },
    {
        "name": "TV Browser Proxy",
        "category": "Apps",
        "mode": "Advanced",
        "level": "Standard",
        "description": "Open a wrapped web page from the PC with browser control and filtering.",
        "action": "browser",
    },
    {
        "name": "PC Screen Mirror",
        "category": "Mirror",
        "mode": "Advanced",
        "level": "Standard",
        "description": "Mirror the PC screen to the TV with adjustable resolution and FPS.",
        "action": "mirror",
    },
    {
        "name": "Reverse Mirror Toggle",
        "category": "Mirror",
        "mode": "Developer",
        "level": "Advanced",
        "description": "Toggle a reverse camera-style link from TV to PC when supported by the TV/browser. This is disabled by default for safety.",
        "action": "reverse_mirror",
    },
    {
        "name": "Network Debugger",
        "category": "Tools",
        "mode": "Developer",
        "level": "Advanced",
        "description": "Probe ports, SSDP discovery, and SmartCast connection info for troubleshooting.",
        "action": "network",
    },
    {
        "name": "Packet Inspector",
        "category": "Tools",
        "mode": "Developer",
        "level": "Advanced",
        "description": "Inspect TV API traffic between the PC and the TV for debugging.",
        "action": "packets",
    },
    {
        "name": "Scenes & Macros",
        "category": "Automation",
        "mode": "Advanced",
        "level": "Standard",
        "description": "Create one-click scripts for power, apps, waits, and input switching.",
        "action": "scenes",
    },
    {
        "name": "Backup Settings",
        "category": "Tools",
        "mode": "Quick",
        "level": "Basic",
        "description": "Save and restore TV settings to a JSON backup file.",
        "action": "backup",
    },
    {
        "name": "Wake-on-LAN",
        "category": "Connect",
        "mode": "Advanced",
        "level": "Advanced",
        "description": "Wake the TV over LAN if your model supports it.",
        "action": "wake",
    },
    {
        "name": "Update Checker",
        "category": "Settings",
        "mode": "Quick",
        "level": "Basic",
        "description": "Check GitHub releases and update the app safely if a newer version is available.",
        "action": "update",
    },
    {
        "name": "Installer Config",
        "category": "Settings",
        "mode": "Quick",
        "level": "Basic",
        "description": "Route the app to the installer and proper desktop/start menu entries.",
        "action": "installer",
    },
    {
        "name": "Advanced Guide",
        "category": "Help",
        "mode": "Developer",
        "level": "Basic",
        "description": "Read the built-in guide and examples for keyboard, scenes, and plugin creation.",
        "action": "guide",
    },
]

CATEGORIES = ["All", "Connect", "Remote", "Apps", "Mirror", "Tools", "Automation", "Settings", "Help"]
MODES = ["All", "Quick", "Advanced", "Developer"]
LEVELS = ["All", "Basic", "Standard", "Advanced"]


class FeaturePackApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_NAME} Feature Pack")
        self.root.geometry("1040x700")
        self.root.minsize(900, 620)
        self.search_var = tk.StringVar()
        self.mode_var = tk.StringVar(value="All")
        self.level_var = tk.StringVar(value="All")
        self.category_var = tk.StringVar(value="All")
        self.update_status = tk.StringVar(value="Checking for updates...")
        self._build_ui()
        self._populate_tool_list()
        self._check_for_updates_async()

    def _build_ui(self):
        top = ttk.Frame(self.root, padding=(12, 10, 12, 8))
        top.pack(fill="x")

        ttk.Label(top, text="Search:").pack(side="left")
        ttk.Entry(top, textvariable=self.search_var, width=30).pack(side="left", padx=(8, 8))

        ttk.Label(top, text="Mode:").pack(side="left")
        ttk.Combobox(top, textvariable=self.mode_var, values=MODES, width=12, state="readonly").pack(side="left", padx=(4, 10))

        ttk.Label(top, text="Level:").pack(side="left")
        ttk.Combobox(top, textvariable=self.level_var, values=LEVELS, width=12, state="readonly").pack(side="left", padx=(4, 10))

        ttk.Label(top, text="Category:").pack(side="left")
        ttk.Combobox(top, textvariable=self.category_var, values=CATEGORIES, width=15, state="readonly").pack(side="left", padx=(4, 10))

        ttk.Button(top, text="Refresh", command=self._populate_tool_list).pack(side="left")
        ttk.Button(top, text="Check for updates", command=self._manual_update_check).pack(side="left", padx=(8, 0))

        status_bar = ttk.Frame(self.root)
        status_bar.pack(fill="x", padx=12, pady=(0, 8))
        ttk.Label(status_bar, textvariable=self.update_status, foreground="#3d5afe").pack(anchor="w")

        split = ttk.Panedwindow(self.root, orient="horizontal")
        split.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        left = ttk.Frame(split, padding=8)
        split.add(left, weight=1)

        right = ttk.Frame(split, padding=8)
        split.add(right, weight=2)

        ttk.Label(left, text="Feature list", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 6))
        self.tool_list = tk.Listbox(left, height=24, exportselection=False, font=("Consolas", 10))
        self.tool_list.pack(fill="both", expand=True)
        self.tool_list.bind("<<ListboxSelect>>", self._on_tool_select)

        ttk.Label(right, text="Selected feature", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 6))
        self.detail = tk.Text(right, wrap="word", state="disabled", font=("Segoe UI", 10))
        self.detail.pack(fill="both", expand=True)

        self.search_var.trace_add("write", lambda *_: self._populate_tool_list())
        self.mode_var.trace_add("write", lambda *_: self._populate_tool_list())
        self.level_var.trace_add("write", lambda *_: self._populate_tool_list())
        self.category_var.trace_add("write", lambda *_: self._populate_tool_list())

    def _matches(self, tool):
        query = self.search_var.get().strip().lower()
        mode = self.mode_var.get()
        level = self.level_var.get()
        category = self.category_var.get()

        if query and query not in " ".join([tool["name"], tool["category"], tool["description"], tool["mode"], tool["level"]]).lower():
            return False
        if mode != "All" and tool["mode"] != mode:
            return False
        if level != "All" and tool["level"] != level:
            return False
        if category != "All" and tool["category"] != category:
            return False
        return True

    def _populate_tool_list(self):
        self.tool_list.delete(0, "end")
        visible = [tool for tool in FEATURES if self._matches(tool)]
        for tool in visible:
            label = f"[{tool['category']}] {tool['name']} ({tool['mode']} / {tool['level']})"
            self.tool_list.insert("end", label)
        if visible:
            self.tool_list.select_set(0)
            self._on_tool_select()
        else:
            self._set_detail("No features match the current filters. Try a broader search or reset the mode filters.")

    def _tool_for_selection(self):
        idx = self.tool_list.curselection()
        if not idx:
            return None
        selected_label = self.tool_list.get(idx[0])
        for tool in FEATURES:
            label = f"[{tool['category']}] {tool['name']} ({tool['mode']} / {tool['level']})"
            if label == selected_label:
                return tool
        return None

    def _on_tool_select(self, *_):
        tool = self._tool_for_selection()
        if not tool:
            return
        body = (
            f"Name: {tool['name']}\n"
            f"Category: {tool['category']}\n"
            f"Mode: {tool['mode']}\n"
            f"Level: {tool['level']}\n\n"
            f"Description:\n{tool['description']}\n\n"
            f"Recommended use:\nUse this in {tool['mode']} mode to keep the interface uncluttered while still exposing the right controls."
        )
        self._set_detail(body)

    def _set_detail(self, text):
        self.detail.config(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", text)
        self.detail.config(state="disabled")

    def _check_for_updates_async(self):
        thread = threading.Thread(target=self._check_for_updates, daemon=True)
        thread.start()

    def _check_for_updates(self):
        try:
            with urllib.request.urlopen(GITHUB_RELEASE_URL, timeout=12) as resp:
                payload = json.loads(resp.read().decode("utf-8", "replace"))
            tag = payload.get("tag_name") or "unknown"
            is_new = self._compare_versions(tag, APP_VERSION)
            if is_new:
                msg = f"Update available: {tag}"
            else:
                msg = f"Up to date: {APP_VERSION}"
        except Exception:
            msg = "Unable to check for updates right now."
        self.root.after(0, lambda: self.update_status.set(msg))

    def _manual_update_check(self):
        self.update_status.set("Checking for updates...")
        self._check_for_updates_async()

    @staticmethod
    def _compare_versions(remote, local):
        def norm(value):
            match = re.search(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?", str(value) or "0")
            if not match:
                return (0, 0, 0)
            return tuple(int(part or 0) for part in match.groups())

        return norm(remote) > norm(local)

    def launch(self):
        self.root.mainloop()


def _open_installer():
    candidate = [
        os.path.join(os.getcwd(), "INSTALL.bat"),
        os.path.join(os.getcwd(), "install.bat"),
    ]
    for path in candidate:
        if os.path.exists(path):
            if os.name == "nt":
                os.startfile(path)
            else:
                subprocess.Popen(["bash", path])
            return
    messagebox.showinfo("Installer", "No installer script was found in the current folder.")


def _show_guide():
    guide = """
Vizio Control Feature Pack Guide
=================================

Quick mode
- Best for simple remote and connect tasks.
- Keeps the experience clean and action-focused.

Advanced mode
- Enables deeper app launching, browser control, and networking tools.
- Good for power users and TV troubleshooting.

Developer mode
- Shows packet inspection, network debugger, and reverse preview controls.
- Enables more advanced tooling.

Reverse mirror
- Off by default.
- Only usable when the TV/browser supports the reverse-screen handshake.
- It is not a guaranteed feature on all Vizio TVs.

Update checker
- Checks the latest GitHub release and warns if a newer version is available.
- Keeps the app current without replacing your saved settings.

Search / category filter
- Type a keyword to instantly narrow the tool list.
- Use the mode and level filters to show only the relevant features.
"""
    messagebox.showinfo("Advanced Guide", guide)


def main():
    root = tk.Tk()
    app = FeaturePackApp(root)
    menubar = tk.Menu(root)
    file_menu = tk.Menu(menubar, tearoff=0)
    file_menu.add_command(label="Open installer", command=_open_installer)
    file_menu.add_separator()
    file_menu.add_command(label="Exit", command=root.destroy)
    menubar.add_cascade(label="File", menu=file_menu)

    tools_menu = tk.Menu(menubar, tearoff=0)
    tools_menu.add_command(label="Reset filters", command=lambda: (
        app.search_var.set(""),
        app.mode_var.set("All"),
        app.level_var.set("All"),
        app.category_var.set("All"),
    ))
    tools_menu.add_command(label="Open guide", command=_show_guide)
    menubar.add_cascade(label="Tools", menu=tools_menu)
    root.config(menu=menubar)

    app.root.after(250, lambda: app._populate_tool_list())
    app.launch()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Feature Pack Error", f"{exc}")
        root.destroy()
