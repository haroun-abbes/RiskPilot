import os
import tempfile

import pytest

_TMP = tempfile.mkdtemp(prefix="riskpilot_test_")
os.environ["RISKPILOT_DATA_DIR"] = _TMP
os.environ.pop("DATABASE_URL", None)


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from riskpilot.main import app

    with TestClient(app) as c:
        yield c
