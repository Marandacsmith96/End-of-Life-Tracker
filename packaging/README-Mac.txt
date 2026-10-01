Quality-of-Life Tracker (Mac)

There are two Mac downloads: one for Apple silicon (M1 or newer, 2020 on)
and one for Intel Macs. If the app says "Bad CPU type", you have the other
kind; download the matching ZIP.
=============================

1. Double-click "Start.command".
   A Terminal window opens and shows an address like http://127.0.0.1:5000/.
   Your web browser should open on it by itself; if it doesn't, open your
   browser and type that address in.
   Leave the Terminal window open while you use the app; closing it stops the app.

2. The first time, macOS may say the app "cannot be opened because the
   developer cannot be verified" (it isn't signed with an Apple account).
   Open System Settings > Privacy & Security, scroll down, and click
   "Open Anyway" next to the message about PetQoLTracker. Then double-click
   Start.command again. On older macOS, right-click Start.command and
   choose Open instead.

Your entries are saved in the "data" folder inside this folder.
Keep the whole folder together. Back up from the More page now and then.

To try it with sample pets first, open Terminal in this folder and run:
  ./PetQoLTracker --seed-demo

Updating to a newer version: download the ZIP again, unzip it, then move your
"data" folder from the old folder into the new one. That folder holds all your
entries and photos.
