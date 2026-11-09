"""A deliberately small Tkinter front end over the CLI commands.

Every button runs the same code as the matching `fcmh` command and prints the
output in the window. Anything that deletes or restores files stays in the CLI
(or runs as a dry run here), so the GUI can't surprise you.
"""

from __future__ import annotations


def run(ledger_path: str) -> int:
    try:
        import tkinter as tk
        from tkinter import scrolledtext
    except ImportError:
        print("Tkinter isn't available in this Python. Install Python from python.org (it includes Tkinter) "
              "or use the fcmh commands instead.")
        return 1

    from fcmh.cli import main
    from fcmh.ui import UI

    root = tk.Tk()
    root.title("fc-mod-helper")
    root.geometry("860x560")

    output = scrolledtext.ScrolledText(root, wrap="word", font=("Consolas", 10))

    def write(text: str) -> None:
        output.insert("end", text + "\n")
        output.see("end")
        root.update_idletasks()

    def no_input(prompt: str) -> str:
        write(prompt + "(answer in the terminal version; GUI skips)")
        return ""

    def runner(*argv: str):
        def _run() -> None:
            output.delete("1.0", "end")
            write("> fcmh " + " ".join(argv))
            ui = UI(out=write, ask=no_input)
            code = main(["--ledger", ledger_path, *argv], ui=ui)
            write(f"\n(exit code {code})")
        return _run

    buttons = [
        ("Ledger", runner("show")),
        ("Pre-launch check", runner("check")),
        ("Conflicts", runner("conflicts")),
        ("Detect build", runner("detect")),
        ("Post-patch (dry run)", runner("post-patch", "--dry-run", "--no-open")),
        ("Rescan (dry run)", runner("rescan", "--dry-run")),
        ("Back up now", runner("backup", "create", "--label", "gui")),
        ("List backups", runner("backup", "list")),
        ("Academy report", runner("academy", "report")),
        ("Online checklist", runner("online-checklist")),
    ]
    bar = tk.Frame(root)
    for index, (label, command) in enumerate(buttons):
        tk.Button(bar, text=label, command=command, width=20).grid(row=index // 5, column=index % 5, padx=3, pady=3)
    bar.pack(side="top", fill="x", padx=6, pady=6)
    output.pack(side="top", fill="both", expand=True, padx=6, pady=(0, 6))
    write("fc-mod-helper. Offline Career Mode only. Deleting and restoring stay in the command line on purpose.")
    write(f"Ledger: {ledger_path}")
    root.mainloop()
    return 0
