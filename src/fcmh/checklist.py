"""'Vanilla for online' checklist. Prints steps only; never changes anything."""

ONLINE_CHECKLIST = """\
Vanilla-for-online checklist (fcmh only prints this; it changes nothing)

EA's rules don't allow mods. Mods and Live Editor are for OFFLINE Career Mode only.
Never enter Ultimate Team, Clubs, Rush, Seasons or any online mode with mods or
Live Editor active. Do these steps before you play online:

 1. Save and quit Career Mode, then close FC completely.
 2. Close FIFA Mod Manager and Live Editor. Check the system tray and Task Manager.
 3. In the EA app, open FC > Manage > Properties and remove "-dataPath FIFAModData"
    (and any other launch argument a mod tool added). Save.
 4. Optional but safest: back up first (fcmh backup create), then rename or delete the
    FIFAModData folder in the game folder so nothing can load it by accident.
 5. If the EA app is in Offline mode, switch it back to Online.
 6. If anything looks wrong, use EA app > Library > FC > Manage > Repair.
 7. Launch FC from the EA app (not from Mod Manager) and confirm the game looks vanilla.

To go back to modded Career Mode: EA app Offline mode, launch from Mod Manager,
and run `fcmh check` first.
"""
