import sys
from os import path

sys.dont_write_bytecode = True
mydir = path.abspath(path.dirname(sys.argv[0]) or ".")
sys.path[:] = [mydir] + [
    p
    for p in sys.path
    if path.isabs(p)
    and path.exists(p)
    and not (path.samefile(p, ".") or path.samefile(p, mydir))
]

if __name__ == "__main__":
    import cp2077gui

    cp2077gui.DatamineVirtuosoFixer()
