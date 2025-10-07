import json
from pathlib import Path

import schemathesis

from app.main import app

SPEC_PATH = Path("api/openapi/openapi.json")

with SPEC_PATH.open("r", encoding="utf-8") as f:
    spec_dict = json.load(f)

schema = schemathesis.from_dict(spec_dict)


@schema.parametrize()
def test_api_contract(case):
    response = case.call_asgi(app)
    case.validate_response(response)
