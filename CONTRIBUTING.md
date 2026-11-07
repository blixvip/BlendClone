# Contributing

> 💬 **Before you open a PR, join the [blix open source Discord](https://discord.gg/wJfHQXfEMM).** It's the home for contributors across every blixvip repo: ask questions, run ideas by us, and talk through your PR.

1. `py -3.12 -m venv .venv && .venv\Scripts\python.exe -m pip install -r requirements.lock.txt`
2. Make the change. Keep the model's output declarative: new capabilities go into `app/models.py` (contract) and `app/blender_scene.py` (compiler), never into executed model text.
3. Add or update tests under `tests/`, then run `python -m pytest`.
4. If rendering changed, run `scripts/renderer_check.py`; if the UI changed, run `scripts/browser_check.py`.
5. Open a PR using the template.

Do not commit reference footage you do not own, `.blend` files, or anything under `data/`, `outputs/`, `originals/` or `logs/`.
