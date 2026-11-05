# BlendClone agent notes

Independent local Blender reconstruction app. All work stays in this repository.

- Backend checks: `.venv/Scripts/python.exe -m pytest` (CI runs the same on Windows).
- UI checks: `.venv/Scripts/python.exe scripts/browser_check.py` with the app running; inspect desktop and narrow screenshots.
- Use declarative, validated scene data. Never execute model-authored Python.
- Generated geometry and animation must stay editable in exported Blender projects.
- Never claim a successful render proves visual fidelity. Disclose approximations.
- Only cancel exact child process handles owned by a BlendClone job; never kill unrelated processes.
- Third-party reference footage stays local (`originals/`, gitignored). Do not commit it.
