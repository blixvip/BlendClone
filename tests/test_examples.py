import json
from pathlib import Path

import pytest

from app.anatomy import expand_assets
from app.models import Plan, validate_timing

EXAMPLES = sorted((Path(__file__).resolve().parents[1] / 'examples').glob('*.json'))


@pytest.mark.parametrize('path', EXAMPLES, ids=lambda p: p.stem)
def test_example_scenes_pass_the_contract(path):
    plan = Plan.model_validate(json.loads(path.read_text(encoding='utf-8')))
    validate_timing(plan, max(shot.end for shot in plan.shots))
    expand_assets(plan)
