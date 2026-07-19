from __future__ import annotations

from pathlib import Path


def choose_directory(title: str, initial_path: str = "") -> Path | None:
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        selected = filedialog.askdirectory(
            initialdir=initial_path or None,
            title=title,
            mustexist=True,
        )
        return Path(selected).resolve() if selected else None
    finally:
        root.destroy()


def choose_save_file(
    title: str,
    suggested_name: str,
    default_extension: str,
    file_types: list[tuple[str, str]],
) -> Path | None:
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        selected = filedialog.asksaveasfilename(
            title=title,
            defaultextension=default_extension,
            initialfile=suggested_name,
            filetypes=file_types,
        )
        return Path(selected).resolve() if selected else None
    finally:
        root.destroy()
