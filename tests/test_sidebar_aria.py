import json
import shutil
import subprocess
from pathlib import Path

import pytest

APP_JS = Path(__file__).resolve().parents[1] / "web" / "app.js"

# Runs the real renderLibrary() from web/app.js against a minimal DOM stub and
# reports which rendered project buttons carry aria-current.
HARNESS = """
const render = __RENDER__;
class Node {
  constructor(tag) { this.tagName = tag; this.attrs = {}; this.children = []; this.className = ''; this.textContent = ''; this.value = ''; }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  append(...nodes) { this.children.push(...nodes); }
  addEventListener() {}
}
const nodes = { search: new Node('input'), library: new Node('div'), 'project-count': new Node('span') };
nodes.library.replaceChildren = fragment => { nodes.library.children = fragment.children.slice(); };
const document = {
  createElement: tag => new Node(tag),
  createDocumentFragment: () => new Node('#fragment'),
};
const $ = id => nodes[id];
const text = (id, value) => { $(id).textContent = value; };
const location = { hash: '' };
const state = {
  jobs: [
    { id: 'a', title: 'Alpha', status: 'preview', created: '2026-11-01T12:00:00Z' },
    { id: 'b', title: 'Beta', status: 'completed', created: '2026-11-02T12:00:00Z' },
    { id: 'c', title: 'Gamma', status: 'queued', created: '2026-11-03T12:00:00Z' },
  ],
  active: { id: 'b' },
};
const run = new Function('state', 'document', '$', 'text', 'location', render + '\\nrenderLibrary();');
function snapshot() {
  const out = {};
  for (const button of nodes.library.children) {
    out[button.children[0].textContent] = button.attrs['aria-current'] ?? null;
  }
  return out;
}
run(state, document, $, text, location);
const withOpen = snapshot();
state.active = null;
run(state, document, $, text, location);
const withNone = snapshot();
process.stdout.write(JSON.stringify({ withOpen, withNone }));
"""


def test_sidebar_marks_only_open_project_with_aria_current():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required to run the sidebar DOM check")
    source = APP_JS.read_text(encoding="utf-8")
    start = source.index("function renderLibrary()")
    end = source.index("async function refreshJobs()")
    program = HARNESS.replace("__RENDER__", json.dumps(source[start:end]))
    completed = subprocess.run([node, "-"], input=program, capture_output=True, text=True, timeout=30, check=True)
    result = json.loads(completed.stdout)
    assert result["withOpen"] == {"Alpha": None, "Beta": "true", "Gamma": None}, \
        "open project is not marked for assistive technology"
    assert result["withNone"] == {"Alpha": None, "Beta": None, "Gamma": None}, \
        "open project is not marked for assistive technology"
