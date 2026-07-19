"""Unit tests for the shared common core."""
import pytest
from fastapi.testclient import TestClient

from common.api import api_key_auth, make_app, mount_dashboard  # noqa: F401
from common.registry import Registry, severity_bands


def test_registry_register_and_get():
    reg = Registry("thing")
    @reg.register("a", weight=5)
    def fn():
        return 42
    assert reg.get("a")() == 42
    assert reg.entry("a").meta["weight"] == 5
    assert reg.names() == ["a"]


def test_registry_unknown_raises():
    reg = Registry("thing")
    with pytest.raises(KeyError):
        reg.get("missing")
    with pytest.raises(KeyError):
        reg.entry("missing")


def test_registry_pop_is_dict_compatible():
    reg = Registry("thing")
    reg.register("x")(lambda: None)
    assert reg.pop("x") is not None
    assert reg.pop("x", None) is None  # default arg, no error


def test_severity_bands():
    assert severity_bands(100, high=50, medium=10) == "high"
    assert severity_bands(20, high=50, medium=10) == "medium"
    assert severity_bands(5, high=50, medium=10) == "low"


def test_make_app_health():
    app = make_app("Test", "desc", "0.1.0")
    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok"}
    assert app.title == "Test"


def test_api_key_auth_disabled_when_no_keys():
    check = api_key_auth(None, None)
    assert check("operator", None) == "anonymous"


def test_api_key_auth_roles():
    check = api_key_auth("v", "o")
    import fastapi
    with pytest.raises(fastapi.HTTPException) as e:
        check("viewer", None)
    assert e.value.status_code == 401
    with pytest.raises(fastapi.HTTPException) as e:
        check("viewer", "bad")
    assert e.value.status_code == 403
    with pytest.raises(fastapi.HTTPException) as e:
        check("operator", "v")  # viewer key on operator route
    assert e.value.status_code == 403
    assert check("viewer", "v") == "viewer"
    assert check("viewer", "o") == "operator"
    assert check("operator", "o") == "operator"
