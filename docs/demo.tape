# Terminal GIF script for the README.
#
# NOTE: VHS is *nix-oriented and Sifty is Windows-only, so VHS is awkward here.
# The practical path on Windows is to RECORD MANUALLY with ScreenToGif
# (winget install NickeManarin.ScreenToGif) while running the commands below in
# Windows Terminal — this file then doubles as the shot-list / timing guide.
# If you do have VHS working: vhs docs/demo.tape  ->  docs/demo.gif

Output docs/demo.gif

Set Shell pwsh
Set FontSize 16
Set Width 1280
Set Height 760
Set Padding 16
Set Theme "Tokyo Night"

# --- One-scan-everything: the value proposition up front -----------------
Type "sifty checkup"  Sleep 700ms  Enter
Sleep 5s

# --- Junk scan: reclaimable space per category ---------------------------
Type "sifty junk scan"  Sleep 700ms  Enter
Sleep 4s

# --- Disk volumes --------------------------------------------------------
Type "sifty disk volumes"  Sleep 700ms  Enter
Sleep 3s

# --- The interactive TUI -------------------------------------------------
Type "sifty tui"  Sleep 700ms  Enter
Sleep 3s
Down  Sleep 1s          # move down the sidebar (Clean)
Enter Sleep 2s
Down  Sleep 1s          # Disk
Enter Sleep 2s
Down  Sleep 1s          # Apps
Enter Sleep 2s
Ctrl+P  Sleep 1500ms    # command palette
Type "ai"  Sleep 1500ms
Escape  Sleep 1s
Type "q"                # quit the TUI
Sleep 2s
