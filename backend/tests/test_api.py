"""Tests for the FastAPI application."""

import ast
import json
import os
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient
from src.main import (
    app,
    _cache,
    _categorize,
    _find_example_files,
    _parse_functions,
    _resolve_type_name,
    _extract_doc,
    _get_default_repr,
    _gh_headers,
)

client = TestClient(app)

# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

SAMPLE_DAGGER_JSON = {
    "name": "gcp-auth",
    "description": "GCP authentication module",
    "engineVersion": "v0.20.3",
    "sdk": {"source": "python"},
    "dependencies": [
        {"name": "oidc-token", "source": "github.com/telchak/daggerverse/oidc-token"}
    ],
}

SAMPLE_README = "# gcp-auth\n\nAuthentication for GCP."

SAMPLE_SOURCE = '''
from typing import Annotated
import dagger
from dagger import Doc, function, object_type, check

@object_type
class GcpAuth:
    """GCP auth module."""

    @function
    @check
    async def validate(
        self,
        credentials: Annotated[dagger.Secret, Doc("Service account JSON")],
        project_id: Annotated[str, Doc("GCP project ID")],
        region: Annotated[str, Doc("GCP region")] = "europe-west1",
        dry_run: Annotated[bool, Doc("Skip actual auth")] = False,
    ) -> str:
        """Validate GCP credentials."""
        pass

    @function
    def with_credentials(
        self,
        container: Annotated[dagger.Container, Doc("Container to configure")],
        token: Annotated[str | None, Doc("Optional OIDC token")] = None,
    ) -> dagger.Container:
        """Add credentials to a container."""
        pass

    def _private_helper(self):
        """Should not appear."""
        pass
'''

SAMPLE_EXAMPLE = '"""Example usage."""\nprint("hello")\n'

# Simulated repo tree (what the Git Trees API returns)
REPO_TREE = [
    {"path": "gcp-auth", "type": "tree"},
    {"path": "gcp-auth/dagger.json", "type": "blob"},
    {"path": "gcp-auth/README.md", "type": "blob"},
    {"path": "gcp-auth/src/gcp_auth/main.py", "type": "blob"},
    {"path": "gcp-auth/examples/python/src/gcp_auth_examples/main.py", "type": "blob"},
    {"path": "_agent_base", "type": "tree"},
    {"path": ".github", "type": "tree"},
]


def _mock_responses():
    """Build mock for httpx.Client.get covering API + raw endpoints."""
    def mock_get(url, **kwargs):
        resp = MagicMock()

        if "/tags" in url:
            resp.status_code = 200
            params = kwargs.get("params", {})
            page = params.get("page", 1)
            if page == 1:
                resp.json.return_value = [
                    {"name": "gcp-auth/v0.2.0"},
                    {"name": "gcp-auth/v0.1.0"},
                ]
            else:
                resp.json.return_value = []

        elif "/git/trees/main" in url:
            resp.status_code = 200
            resp.json.return_value = {"tree": REPO_TREE}

        elif "raw.githubusercontent.com" in url:
            resp.status_code = 200
            if "dagger.json" in url:
                resp.text = json.dumps(SAMPLE_DAGGER_JSON)
            elif "README.md" in url:
                resp.text = SAMPLE_README
            elif "examples" in url and "main.py" in url:
                resp.text = SAMPLE_EXAMPLE
            elif "main.py" in url:
                resp.text = SAMPLE_SOURCE
            else:
                resp.status_code = 404
                resp.text = ""

        else:
            resp.status_code = 404

        return resp
    return mock_get


def _make_mock_client():
    mock_client = MagicMock()
    mock_client.get = MagicMock(side_effect=_mock_responses())
    mock_client.__enter__ = lambda s: mock_client
    mock_client.__exit__ = MagicMock(return_value=False)
    return mock_client


def _reset_cache():
    _cache["modules"] = []
    _cache["details"] = {}
    _cache["categories"] = []
    _cache["ts"] = 0


# ---------------------------------------------------------------------------
# Unit tests — parser functions
# ---------------------------------------------------------------------------


def test_categorize():
    assert _categorize("angie") == "agent"
    assert _categorize("monty") == "agent"
    assert _categorize("gcp-auth") == "infra"
    assert _categorize("gcp-cloud-run") == "infra"
    assert _categorize("oidc-token") == "infra"
    assert _categorize("health-check") == "infra"
    assert _categorize("angular") == "build"
    assert _categorize("python-build") == "build"
    assert _categorize("calver") == "utility"
    assert _categorize("semver") == "utility"


def test_parse_functions_extracts_decorated():
    fns = _parse_functions(SAMPLE_SOURCE)
    names = [f["name"] for f in fns]
    assert "validate" in names
    assert "with_credentials" in names
    assert "_private_helper" not in names


def test_parse_functions_check_and_async():
    fns = _parse_functions(SAMPLE_SOURCE)
    validate = next(f for f in fns if f["name"] == "validate")
    assert validate["is_check"] is True
    assert validate["is_async"] is True

    with_creds = next(f for f in fns if f["name"] == "with_credentials")
    assert with_creds["is_check"] is False
    assert with_creds["is_async"] is False


def test_parse_functions_params():
    fns = _parse_functions(SAMPLE_SOURCE)
    validate = next(f for f in fns if f["name"] == "validate")
    params = {p["name"]: p for p in validate["params"]}

    assert params["credentials"]["type"] == "Secret"
    assert params["credentials"]["required"] is True
    assert params["credentials"]["description"] == "Service account JSON"
    assert params["credentials"]["default"] == ""

    assert params["region"]["type"] == "String"
    assert params["region"]["required"] is False
    assert params["region"]["default"] == '"europe-west1"'

    assert params["dry_run"]["type"] == "Boolean"
    assert params["dry_run"]["required"] is False
    assert params["dry_run"]["default"] == "False"


def test_parse_functions_nullable_param():
    fns = _parse_functions(SAMPLE_SOURCE)
    with_creds = next(f for f in fns if f["name"] == "with_credentials")
    token = next(p for p in with_creds["params"] if p["name"] == "token")
    assert token["required"] is False
    assert token["type"] == "String"


def test_parse_functions_return_type():
    fns = _parse_functions(SAMPLE_SOURCE)
    validate = next(f for f in fns if f["name"] == "validate")
    assert validate["return_type"] == "String"

    with_creds = next(f for f in fns if f["name"] == "with_credentials")
    assert with_creds["return_type"] == "Container"


def test_parse_functions_docstring():
    fns = _parse_functions(SAMPLE_SOURCE)
    validate = next(f for f in fns if f["name"] == "validate")
    assert validate["description"] == "Validate GCP credentials."


def test_parse_functions_syntax_error():
    assert _parse_functions("def broken(") == []


def test_parse_functions_no_functions():
    assert _parse_functions("x = 1\ny = 2\n") == []


def test_get_default_repr_values():
    assert _get_default_repr(ast.Constant(value=None)) == "None"
    assert _get_default_repr(ast.Constant(value="hello")) == '"hello"'
    assert _get_default_repr(ast.Constant(value=True)) == "True"
    assert _get_default_repr(ast.Constant(value=42)) == "42"
    assert _get_default_repr(ast.Name(id="SOME_CONST")) == "SOME_CONST"
    assert _get_default_repr(ast.List(elts=[])) == "[]"
    assert _get_default_repr(ast.Dict(keys=[], values=[])) == "{}"
    assert _get_default_repr(ast.Tuple(elts=[])) == "..."


def test_resolve_type_name_simple():
    assert _resolve_type_name(ast.Name(id="str")) == "String"
    assert _resolve_type_name(ast.Name(id="int")) == "Integer"
    assert _resolve_type_name(ast.Name(id="CustomType")) == "CustomType"
    assert _resolve_type_name(ast.Constant(value="literal")) == "literal"


def test_extract_doc_non_subscript():
    assert _extract_doc(ast.Name(id="str")) == ""


def test_gh_headers_without_token():
    with patch.dict(os.environ, {}, clear=True):
        headers = _gh_headers()
        assert "Authorization" not in headers
        assert headers["Accept"] == "application/vnd.github.v3+json"


def test_gh_headers_with_token():
    with patch.dict(os.environ, {"GITHUB_TOKEN": "ghp_test123"}):
        headers = _gh_headers()
        assert headers["Authorization"] == "Bearer ghp_test123"


def test_find_example_files():
    paths = {
        "mymod/examples/python/src/mymod_examples/main.py",
        "mymod/examples/go/src/mymod_examples/main.go",
        "mymod/examples/python/src/mymod_examples/__init__.py",
        "mymod/src/mymod/main.py",
    }
    result = _find_example_files(paths, "mymod")
    langs = {lang for lang, _ in result}
    assert "python" in langs
    assert "go" in langs
    assert len(result) == 2


def test_find_example_files_none():
    result = _find_example_files({"mymod/src/main.py"}, "mymod")
    assert result == []


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "module-catalog-api"


@patch("src.main.httpx.Client")
def test_list_items(mock_client_cls):
    _reset_cache()
    mock_client_cls.return_value = _make_mock_client()

    response = client.get("/api/items")
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert items[0]["name"] == "gcp-auth"
    assert items[0]["category"] == "infra"
    assert items[0]["sdk"] == "python"
    assert items[0]["version"] == "v0.2.0"
    assert "dagger install" in items[0]["install_command"]


@patch("src.main.httpx.Client")
def test_list_categories(mock_client_cls):
    _reset_cache()
    mock_client_cls.return_value = _make_mock_client()

    response = client.get("/api/categories")
    assert response.status_code == 200
    cats = response.json()
    assert "infra" in cats


@patch("src.main.httpx.Client")
def test_get_item_detail(mock_client_cls):
    _reset_cache()
    mock_client_cls.return_value = _make_mock_client()

    client.get("/api/items")

    response = client.get("/api/items/gcp-auth")
    assert response.status_code == 200
    detail = response.json()
    assert detail["name"] == "gcp-auth"
    assert detail["readme"] == SAMPLE_README
    assert len(detail["dependencies"]) == 1
    assert detail["dependencies"][0]["name"] == "oidc-token"


@patch("src.main.httpx.Client")
def test_get_item_detail_has_functions(mock_client_cls):
    _reset_cache()
    mock_client_cls.return_value = _make_mock_client()

    client.get("/api/items")
    response = client.get("/api/items/gcp-auth")
    detail = response.json()

    assert len(detail["functions"]) == 2
    fn_names = [f["name"] for f in detail["functions"]]
    assert "validate" in fn_names
    assert "with_credentials" in fn_names

    validate = next(f for f in detail["functions"] if f["name"] == "validate")
    assert validate["is_check"] is True
    assert len(validate["params"]) == 4


@patch("src.main.httpx.Client")
def test_get_item_detail_has_examples(mock_client_cls):
    _reset_cache()
    mock_client_cls.return_value = _make_mock_client()

    client.get("/api/items")
    response = client.get("/api/items/gcp-auth")
    detail = response.json()

    assert len(detail["examples"]) == 1
    assert detail["examples"][0]["language"] == "python"
    assert "Example usage" in detail["examples"][0]["code"]


def test_get_item_not_found():
    response = client.get("/api/items/nonexistent-module")
    assert response.status_code == 404


@patch("src.main.httpx.Client")
def test_cache_hit_skips_fetch(mock_client_cls):
    """Second call within TTL should use cache, not call GitHub again."""
    _reset_cache()
    mock_client = _make_mock_client()
    mock_client_cls.return_value = mock_client

    client.get("/api/items")
    first_call_count = mock_client.get.call_count

    client.get("/api/items")
    assert mock_client.get.call_count == first_call_count
