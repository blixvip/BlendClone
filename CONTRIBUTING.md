# Contributing

> 💬 **Before you open a PR, join the [blix open source Discord](https://discord.gg/grokbot).** It's the home for contributors across every blixvip repo: ask questions, run ideas by us, and talk through your PR.

## Your first PR in 10 minutes

You don't need Blender, FFmpeg or a ChatGPT account: the test suite mocks them.

1. **Get the code.** Either [open a Codespace](https://codespaces.new/blixvip/BlendClone?quickstart=1) (Python 3.12, FFmpeg and dependencies preinstalled, skip step 2), or fork and clone:
   `git clone https://github.com/<you>/BlendClone.git && cd BlendClone`
2. **Install** (Python 3.12):
   - Linux/macOS: `python3.12 -m venv .venv && .venv/bin/python -m pip install -r requirements.lock.txt`
   - Windows: `py -3.12 -m venv .venv && .venv\Scripts\python.exe -m pip install -r requirements.lock.txt`
3. **Run the tests:** `python -m pytest` (inside the venv). Tests that need FFmpeg are skipped automatically if it isn't installed.
4. **Pick an issue:** browse [good first issues](https://github.com/blixvip/BlendClone/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22) (each names the files to touch) and comment to claim one.
5. **Open a PR:** branch, make the change with a test, run `python -m pytest` again, push, and open a PR using the template.

## Details

1. `py -3.12 -m venv .venv && .venv\Scripts\python.exe -m pip install -r requirements.lock.txt`
2. Make the change. Keep the model's output declarative: new capabilities go into `app/models.py` (contract) and `app/blender_scene.py` (compiler), never into executed model text.
3. Add or update tests under `tests/`, then run `python -m pytest`.
4. If rendering changed, run `scripts/renderer_check.py`; if the UI changed, run `scripts/browser_check.py`.
5. Open a PR using the template.

Do not commit reference footage you do not own, `.blend` files, or anything under `data/`, `outputs/`, `originals/` or `logs/`.
