# Cyberpunk Python Hacks

This repository contains python scripts to manipulate Cyberpunk 2077
save files.
To use these scripts you need to install [Python](https://python.org)
first.
By default old save files are backed up at the same directory with name
`backup_1.dat`, `backup_2.dat`, ... .

To fix [Datamine Virtuoso bug](
https://forums.cdprojektred.com/index.php?threads/not-getting-quickhacks-from-access-points.11061788/
) you need to simply run (or double click) `datamine-virtuoso-fixer.pyw`
file.
After loading the save file, it shows `failedShardDrops` field value:

![Datamine Virtuoso Fixer](screenshots/datamine-virtuoso-fixer.png)

Now you can fix the save file by clicking the `Fix File` button.
