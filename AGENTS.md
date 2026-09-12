# BlendRemake

Independent local Blender reconstruction app. All work stays in this repository.
Never modify or depend on MotionClone / frameforge-local / motionclone-waitlist.
Never close, stop, restart, or kill Warp, its windows, tabs, panes, or processes.
Only cancel exact child process handles owned by a BlendRemake job.

Read C:/code/UI-PLAYBOOK.md before UI work. Capture and inspect desktop and narrow screenshots.
Run `.venv/Scripts/python.exe -m pytest -q` for backend checks.
Run `.venv/Scripts/python.exe scripts/browser_check.py` with the app running for UI checks.
Use declarative validated scene data: never execute model-authored Python.
Generated geometry and animation must stay editable in exported Blender projects.
Never claim a successful render proves visual fidelity. Disclose approximations.
