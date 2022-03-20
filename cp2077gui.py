from os import environ
from pathlib import Path
from sys import argv
from tkinter import N, W, S, E, Listbox, StringVar, Tk
from tkinter.ttk import Button, Entry, Frame, Label
from cp2077save import SaveFile

SEARCH_PATH = "Saved Games", "CD Projekt Red", "Cyberpunk 2077"
HOME = environ.get("USERPROFILE") if len(argv) < 2 else argv[1]
HOME = Path(HOME or ".").resolve(strict=True)
if HOME.joinpath(*SEARCH_PATH).is_dir():
    HOME = HOME.joinpath(*SEARCH_PATH)
elif HOME.joinpath(*SEARCH_PATH[1:]).is_dir():
    HOME = HOME.joinpath(*SEARCH_PATH[1:])
elif (HOME / SEARCH_PATH[-1]).is_dir():
    HOME = HOME / SEARCH_PATH[-1]
if HOME.is_file():
    HOME = HOME.parent
if not HOME.is_dir():
    raise Exception


def get_savefiles():
    res = []
    for item in HOME.iterdir():
        try:
            item = SaveFile.summary(item)
        except Exception:
            pass
        else:
            res.append((item.date, item.time, item))
    return [item[-1] for item in sorted(res, reverse=True)]


if (HOME / SaveFile.NAME).is_file() and not get_savefiles():
    HOME = HOME.parent


class Window:
    TITLE = ""
    WIDTH = 600
    HEIGHT = 400

    def __init__(self):
        self.savefiles = tuple(get_savefiles())
        self.root = root = Tk()
        root.title(self.TITLE)
        root.minsize(self.WIDTH // 2, self.HEIGHT // 2)
        root.geometry("%dx%d" % (self.WIDTH, self.HEIGHT))
        root.rowconfigure(0, weight=1)
        root.columnconfigure(0, weight=1)
        frm = Frame(root, padding=10)
        frm.grid(row=0, column=0, sticky=(N, W, S, E))
        self._vars = {}
        self._savefile = None
        self.init(frm)
        root.mainloop()

    @property
    def savefile(self):
        summary = self.selected_savefile()
        if summary is None:
            self._savefile = None
            return None
        res = self._savefile
        if res is None or res.path != summary.path:
            try:
                res = SaveFile(summary.path)
            except Exception:
                res = None
            self._savefile = res
        return res

    def vars(self, name, *args):
        all_vars = self._vars
        if name not in all_vars:
            all_vars[name] = StringVar()
        res = all_vars[name]
        if args:
            value, *default = args
            if len(default) == 1:
                default = default[0]
            if value is None:
                res.set(default or "")
            else:
                res.set(value)
        return res

    def savefile_selectbox(self, parent, row, col, **kw):
        var = StringVar(value=tuple(map(str, self.savefiles)))
        lbox = Listbox(parent, listvariable=var)
        lbox.grid(row=row, column=col, sticky=(N, W, S, E), **kw)
        self._savefile_selectbox = lbox
        for i in range(0, len(self.savefiles), 2):
            lbox.itemconfigure(i, background="#f0f0ff")
        return lbox

    def select_savefile(self, ind):
        savefiles = self.savefiles
        n = len(savefiles)
        try:
            if ind not in range(n):
                ind = savefiles.index(ind)
        except Exception:
            ind = -1
        try:
            lbox = self._savefile_selectbox
            if ind > 0:
                lbox.selection_clear(0, ind - 1)
            if ind < n - 1:
                lbox.selection_clear(ind + 1, n - 1)
            if ind >= 0:
                lbox.selection_set(ind)
        except Exception:
            pass

    def selected_savefile(self):
        ind = None
        try:
            ind = self._savefile_selectbox.curselection()[-1]
        except Exception:
            pass
        try:
            return self.savefiles[ind]
        except Exception:
            return None

    def ro_label_entry(self, parent, title, variable):
        lbl = Label(parent, text=title)
        lbl.grid(column=0, sticky=E)
        row = lbl.grid_info()["row"]
        Entry(
            parent, textvariable=self.vars(variable), state=["readonly"]
        ).grid(row=row, column=1, sticky=(W, E))

    def savefile_detailbox(self, parent, row, col, **kw):
        frm = Frame(parent, padding=10)
        frm.grid(row=row, column=col, sticky=(N, W, S, E), **kw)
        self.ro_label_entry(frm, "Name:", "name")
        self.ro_label_entry(frm, "Game Version:", "version")
        self.ro_label_entry(frm, "Save Date:", "date")
        self.ro_label_entry(frm, "Save Time:", "time")
        return frm

    def update_savefile_summary(self, summary=None):
        setv = self.vars
        setv("name", summary and summary.name)
        setv("version", summary and f"{summary.version / 1000:g}")
        setv("date", summary and summary.date)
        setv("time", summary and summary.time)


class DatamineVirtuosoFixer(Window):
    TITLE = "Cyberpunk Datamine Virtuoso Fixer"

    def init(self, top):
        top.rowconfigure(0, weight=1)
        top.columnconfigure(0, weight=1)
        top.columnconfigure(1, weight=1)
        lbox = self.savefile_selectbox(top, 0, 0, rowspan=2)
        right = Frame(top, padding=10)
        right.grid(row=0, column=1, sticky=(N, W, E))
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)
        right.columnconfigure(1, weight=1)
        self.savefile_detailbox(right, 0, 0, columnspan=2)
        self.btn_load = Button(
            right, text="Load File", command=self.load_file
        )
        self.btn_fix = Button(
            right, text="Fix File", command=self.fix_file
        )
        self.btn_load.grid(row=1, column=0)
        self.btn_fix.grid(row=1, column=1)
        self.select_savefile(0)
        self.selection_changed()
        lbox.bind("<<ListboxSelect>>", self.selection_changed)

    def selection_changed(self, *args):
        enable = "!disabled"
        summary = self.selected_savefile()
        if summary is None:
            enable = enable[1:]
        self.btn_load.state([enable])
        self.btn_fix.state(["disabled"])
        self.update_savefile_summary(summary)

    def load_file(self):
        self.btn_load.state(["disabled"])
        self._savefile = None
        if self.savefile is None:
            self.btn_load.state(["!disabled"])
        else:
            self.btn_fix.state(["!disabled"])

    def fix_file(self):
        self.btn_load.state(["disabled"])
        self.btn_fix.state(["disabled"])
