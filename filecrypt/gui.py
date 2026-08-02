"""tkinter front end.

tkinter ships with Python, so this runs on macOS, Linux and Raspberry Pi
without a single wheel to install. That matters more here than looking
native: the whole point is a bundle that works on an air-gapped machine.

Work happens on a worker thread and talks back through a queue, because
the 2021 Qt version did AES on the UI thread and beachballed on anything
larger than a small file. Only the main thread touches widgets.
"""

import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import __version__, core

PAD = {"padx": 8, "pady": 4}


class App(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=12)
        self.grid(sticky="nsew")
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)

        self.events = queue.Queue()
        self.worker = None

        self.password = tk.StringVar()
        self.password2 = tk.StringVar()
        self.salt = tk.StringVar()
        self.salt2 = tk.StringVar()
        self.target = tk.StringVar()
        self.recursive = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Ready.")

        self._build()
        self.after(100, self._drain)

    # ------------------------------------------------------------- layout
    def _build(self):
        r = 0
        for label, var in (("Password", self.password), ("Confirm password", self.password2),
                           ("Salt", self.salt), ("Confirm salt", self.salt2)):
            ttk.Label(self, text=label + ":").grid(row=r, column=0, sticky="e", **PAD)
            ttk.Entry(self, textvariable=var, show="•", width=34).grid(
                row=r, column=1, columnspan=2, sticky="ew", **PAD)
            r += 1

        ttk.Separator(self, orient="horizontal").grid(
            row=r, column=0, columnspan=3, sticky="ew", pady=8)
        r += 1

        ttk.Label(self, text="Target:").grid(row=r, column=0, sticky="e", **PAD)
        ttk.Entry(self, textvariable=self.target).grid(row=r, column=1, sticky="ew", **PAD)
        browse = ttk.Frame(self)
        browse.grid(row=r, column=2, sticky="w", **PAD)
        ttk.Button(browse, text="File…", width=7, command=self._pick_file).pack(side="left")
        ttk.Button(browse, text="Folder…", width=9, command=self._pick_dir).pack(side="left", padx=(4, 0))
        r += 1

        ttk.Checkbutton(self, text="Include subfolders",
                        variable=self.recursive).grid(row=r, column=1, sticky="w", **PAD)
        r += 1

        buttons = ttk.Frame(self)
        buttons.grid(row=r, column=0, columnspan=3, pady=(12, 4))
        self.encrypt_btn = ttk.Button(buttons, text="Encrypt", width=14,
                                      command=lambda: self._start("encrypt"))
        self.encrypt_btn.pack(side="left", padx=6)
        self.decrypt_btn = ttk.Button(buttons, text="Decrypt", width=14,
                                      command=lambda: self._start("decrypt"))
        self.decrypt_btn.pack(side="left", padx=6)
        r += 1

        self.bar = ttk.Progressbar(self, mode="determinate")
        self.bar.grid(row=r, column=0, columnspan=3, sticky="ew", **PAD)
        r += 1
        ttk.Label(self, textvariable=self.status, foreground="#555").grid(
            row=r, column=0, columnspan=3, sticky="w", **PAD)

    def _pick_file(self):
        p = filedialog.askopenfilename(title="Select a file")
        if p:
            self.target.set(p)

    def _pick_dir(self):
        p = filedialog.askdirectory(title="Select a folder")
        if p:
            self.target.set(p)

    # -------------------------------------------------------------- driving
    def _start(self, action):
        if self.worker and self.worker.is_alive():
            return
        pw, salt, target = self.password.get(), self.salt.get(), self.target.get()
        if not pw or not salt or not target:
            messagebox.showwarning("Missing details",
                                   "Password, salt and target are all required.")
            return
        if action == "encrypt":
            if pw != self.password2.get() or salt != self.salt2.get():
                messagebox.showwarning(
                    "Check your entries",
                    "Password and salt must match their confirmation.\n\n"
                    "Nothing verifies these at encrypt time, so a typo here "
                    "would leave the files permanently unreadable.")
                return
        if not os.path.exists(target):
            messagebox.showwarning("Not found", f"{target} does not exist.")
            return

        self._busy(True)
        self.worker = threading.Thread(target=self._run, args=(action, pw, salt, target),
                                       daemon=True)
        self.worker.start()

    def _run(self, action, pw, salt, target):
        say = lambda kind, payload: self.events.put((kind, payload))
        try:
            files = self._collect(action, target)
            if not files:
                say("done", (0, 0, "Nothing to do -- no matching files found."))
                return
            ok = 0
            problems = []
            for i, src in enumerate(files, 1):
                name = os.path.basename(src)
                say("status", f"{action.capitalize()}ing {name} ({i}/{len(files)})")
                try:
                    if action == "encrypt":
                        core.encrypt_file(src, src + core.SUFFIX, pw, salt)
                    else:
                        dst = src[: -len(core.SUFFIX)]
                        if os.path.abspath(dst) == os.path.abspath(src):
                            raise core.CryptError("output would overwrite the input")
                        core.decrypt_file(src, dst, pw, salt)
                    ok += 1
                except (core.CryptError, OSError) as e:
                    problems.append(f"{name}: {e}")
                say("progress", i / len(files) * 100)
            say("done", (ok, len(files), "\n".join(problems)))
        except Exception as e:                                  # noqa: BLE001
            say("error", str(e))

    def _collect(self, action, target):
        want = (lambda n: n.endswith(core.SUFFIX)) if action == "decrypt" \
            else (lambda n: not n.endswith(core.SUFFIX))
        if os.path.isfile(target):
            return [target] if want(os.path.basename(target)) else []
        found = []
        walker = os.walk(target) if self.recursive.get() else \
            [(target, [], os.listdir(target))]
        for root, _dirs, names in walker:
            for n in sorted(names):
                full = os.path.join(root, n)
                if os.path.isfile(full) and not n.startswith(".") and want(n):
                    found.append(full)
        return found

    def _drain(self):
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "status":
                    self.status.set(payload)
                elif kind == "progress":
                    self.bar["value"] = payload
                elif kind == "error":
                    self._busy(False)
                    self.status.set("Failed.")
                    messagebox.showerror("Error", payload)
                elif kind == "done":
                    ok, total, problems = payload
                    self._busy(False)
                    self.bar["value"] = 0
                    if not total:
                        self.status.set(problems)
                    elif problems:
                        self.status.set(f"{ok} of {total} succeeded.")
                        messagebox.showwarning("Some files failed", problems)
                    else:
                        self.status.set(f"Done -- {ok} file(s).")
                        messagebox.showinfo("Finished", f"{ok} file(s) processed.")
        except queue.Empty:
            pass
        self.after(100, self._drain)

    def _busy(self, busy):
        state = "disabled" if busy else "normal"
        self.encrypt_btn.config(state=state)
        self.decrypt_btn.config(state=state)
        if busy:
            self.status.set("Working…")


def main():
    root = tk.Tk()
    root.title(f"FileCrypt {__version__}")
    root.minsize(520, 380)
    App(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
