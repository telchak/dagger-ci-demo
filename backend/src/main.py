"""FastAPI backend service — Dagger module catalog API.

Pulls live module metadata from the telchak/daggerverse GitHub repository.
Uses the Git Trees API (1 call) + raw.githubusercontent.com (no rate limit)
to avoid hitting GitHub's 60 req/hr unauthenticated limit.
"""

import ast
import json
import os
import time

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Module Catalog API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# GitHub integration
# ---------------------------------------------------------------------------

GITHUB_REPO = "telchak/daggerverse"
GITHUB_API = "https://api.github.com"
GITHUB_RAW = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main"
CACHE_TTL_SECONDS = 300

SKIP_DIRS = {"_agent_base", "tests", ".github", ".dagger"}

_cache: dict = {"modules": [], "details": {}, "categories": [], "ts": 0}


def _gh_headers() -> dict[str, str]:
    headers = {"Accept": "application/vnd.github.v3+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _fetch_raw(client: httpx.Client, path: str) -> str | None:
    """Fetch file content via raw.githubusercontent.com (no API rate limit)."""
    resp = client.get(f"{GITHUB_RAW}/{path}")
    if resp.status_code != 200:
        return None
    return resp.text


def _fetch_latest_tags(client: httpx.Client) -> dict[str, str]:
    """Fetch tags via API (1-2 calls) and return module -> latest version map."""
    tags_by_module: dict[str, list[str]] = {}
    page = 1
    while True:
        resp = client.get(
            f"{GITHUB_API}/repos/{GITHUB_REPO}/tags",
            headers=_gh_headers(),
            params={"per_page": 100, "page": page},
        )
        if resp.status_code != 200:
            break
        page_tags = resp.json()
        if not page_tags:
            break
        for tag in page_tags:
            name = tag["name"]
            if "/" in name:
                module, version = name.rsplit("/", 1)
                tags_by_module.setdefault(module, []).append(version)
        page += 1

    latest: dict[str, str] = {}
    for module, versions in tags_by_module.items():
        latest[module] = sorted(versions)[-1]
    return latest


def _fetch_repo_tree(client: httpx.Client) -> list[dict]:
    """Fetch the full repo tree in a single API call (recursive)."""
    resp = client.get(
        f"{GITHUB_API}/repos/{GITHUB_REPO}/git/trees/main",
        headers=_gh_headers(),
        params={"recursive": "1"},
    )
    if resp.status_code != 200:
        return []
    return resp.json().get("tree", [])


# ---------------------------------------------------------------------------
# AST-based function signature parser
# ---------------------------------------------------------------------------

_TYPE_MAP = {
    "str": "String",
    "int": "Integer",
    "bool": "Boolean",
    "float": "Float",
    "Directory": "Directory",
    "File": "File",
    "Container": "Container",
    "Secret": "Secret",
    "Service": "Service",
    "Platform": "Platform",
}


def _resolve_type_name(node: ast.expr) -> str:
    """Extract a human-readable type name from an AST type annotation node."""
    if isinstance(node, ast.Name):
        return _TYPE_MAP.get(node.id, node.id)
    if isinstance(node, ast.Constant):
        return str(node.value)
    if isinstance(node, ast.Attribute):
        return _TYPE_MAP.get(node.attr, node.attr)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        left = _resolve_type_name(node.left)
        right = _resolve_type_name(node.right)
        if right == "None":
            return f"{left} | None"
        return f"{left} | {right}"
    if isinstance(node, ast.Subscript):
        base = _resolve_type_name(node.value)
        if base == "Annotated" and isinstance(node.slice, ast.Tuple):
            return _resolve_type_name(node.slice.elts[0])
        if base == "list":
            inner = _resolve_type_name(node.slice)
            return f"list[{inner}]"
        if base == "Optional":
            return f"{_resolve_type_name(node.slice)} | None"
        return base
    return "any"


def _extract_doc(node: ast.expr) -> str:
    """Extract Doc("...") string from an Annotated slice."""
    if not isinstance(node, ast.Subscript):
        return ""
    if not isinstance(node.slice, ast.Tuple):
        return ""
    for elt in node.slice.elts:
        if isinstance(elt, ast.Call):
            func_name = ""
            if isinstance(elt.func, ast.Name):
                func_name = elt.func.id
            elif isinstance(elt.func, ast.Attribute):
                func_name = elt.func.attr
            if func_name == "Doc" and elt.args:
                if isinstance(elt.args[0], ast.Constant):
                    return str(elt.args[0].value)
    return ""


def _get_default_repr(node: ast.expr) -> str:
    """Get string representation of a default value AST node."""
    if isinstance(node, ast.Constant):
        if node.value is None:
            return "None"
        if isinstance(node.value, str):
            return f'"{node.value}"'
        if isinstance(node.value, bool):
            return str(node.value)
        return str(node.value)
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.List):
        return "[]"
    if isinstance(node, ast.Dict):
        return "{}"
    return "..."


def _parse_functions(source: str) -> list[dict]:
    """Parse a Python source file and extract @function-decorated methods."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    functions = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        has_function_dec = False
        is_check = False
        for dec in node.decorator_list:
            if isinstance(dec, ast.Name) and dec.id == "function":
                has_function_dec = True
            if isinstance(dec, ast.Name) and dec.id == "check":
                is_check = True
        if not has_function_dec:
            continue

        docstring = ast.get_docstring(node) or ""
        return_type = _resolve_type_name(node.returns) if node.returns else "void"

        params = []
        args = node.args
        num_args = len(args.args)
        num_defaults = len(args.defaults)
        default_offset = num_args - num_defaults

        for i, arg in enumerate(args.args):
            if arg.arg == "self":
                continue

            annotation = arg.annotation
            param_type = _resolve_type_name(annotation) if annotation else "any"
            description = _extract_doc(annotation) if annotation else ""

            default_idx = i - default_offset
            has_default = default_idx >= 0
            default_value = ""
            if has_default:
                default_value = _get_default_repr(args.defaults[default_idx])

            is_optional = "None" in param_type or has_default
            display_type = param_type.replace(" | None", "")

            params.append({
                "name": arg.arg,
                "type": display_type,
                "description": description,
                "required": not is_optional,
                "default": default_value if has_default else "",
            })

        functions.append({
            "name": node.name,
            "description": docstring,
            "is_check": is_check,
            "is_async": isinstance(node, ast.AsyncFunctionDef),
            "return_type": return_type,
            "params": params,
        })

    return functions


# ---------------------------------------------------------------------------
# Cache refresh — optimized: 2 API calls + raw file fetches (no rate limit)
# ---------------------------------------------------------------------------

def _categorize(name: str) -> str:
    if name in ("angie", "monty", "daggie", "goose", "speck"):
        return "agent"
    if name.startswith("gcp-") or name in ("oidc-token", "health-check"):
        return "infra"
    if name in ("angular", "python-build"):
        return "build"
    return "utility"


def _find_example_files(tree_paths: set[str], dirname: str) -> list[dict]:
    """Find example main files from the pre-fetched tree."""
    prefix = f"{dirname}/examples/"
    # Find language dirs: examples/{lang}/src/{pkg}/main.py
    example_mains: dict[str, str] = {}
    for path in tree_paths:
        if not path.startswith(prefix):
            continue
        # e.g. gcp-cloud-run/examples/python/src/gcp_cloud_run_examples/main.py
        rest = path[len(prefix):]
        parts = rest.split("/")
        if len(parts) >= 4 and parts[1] == "src" and parts[-1] in ("main.py", "main.go", "index.ts"):
            lang = parts[0]
            if lang not in example_mains:
                example_mains[lang] = path
    return list(example_mains.items())


def _refresh_cache() -> None:
    global _cache

    if time.time() - _cache["ts"] < CACHE_TTL_SECONDS and _cache["modules"]:
        return

    modules = []
    details = {}
    categories_seen: set[str] = set()

    with httpx.Client(timeout=30) as client:
        # 1. Fetch tags (1 API call)
        latest_tags = _fetch_latest_tags(client)

        # 2. Fetch full repo tree (1 API call) — gives us all file paths
        tree = _fetch_repo_tree(client)
        if not tree:
            return

        # Build path sets for fast lookup
        all_paths = {item["path"] for item in tree if item["type"] == "blob"}
        all_dirs = {item["path"] for item in tree if item["type"] == "tree"}

        # Find module directories (top-level dirs with dagger.json)
        top_dirs = set()
        for d in all_dirs:
            if "/" not in d and d not in SKIP_DIRS and not d.startswith("."):
                if f"{d}/dagger.json" in all_paths:
                    top_dirs.add(d)

        # 3. Fetch files via raw.githubusercontent.com (no rate limit!)
        for idx, dirname in enumerate(sorted(top_dirs), start=1):
            raw = _fetch_raw(client, f"{dirname}/dagger.json")
            if raw is None:
                continue

            try:
                dagger_json = json.loads(raw)
            except json.JSONDecodeError:
                continue

            name = dagger_json.get("name", dirname)
            description = dagger_json.get("description", "")
            sdk = dagger_json.get("sdk", {})
            sdk_name = sdk if isinstance(sdk, str) else sdk.get("source", "unknown")
            engine = dagger_json.get("engineVersion", "")
            deps = dagger_json.get("dependencies", [])
            version = latest_tags.get(name, "unreleased")
            category = _categorize(name)
            categories_seen.add(category)

            dep_names = [{"name": d.get("name", ""), "source": d.get("source", "")} for d in deps]
            install_cmd = f"dagger install github.com/{GITHUB_REPO}/{dirname}@{name}/{version}"

            module = {
                "id": idx,
                "name": name,
                "description": description,
                "category": category,
                "sdk": sdk_name,
                "version": version,
                "engine_version": engine,
                "dependencies": dep_names,
                "install_command": install_cmd,
                "github_url": f"https://github.com/{GITHUB_REPO}/tree/main/{dirname}",
                "daggerverse_url": f"https://daggerverse.dev/mod/github.com/{GITHUB_REPO}/{dirname}",
            }
            modules.append(module)

            # Fetch source for function signatures (raw — no rate limit)
            mod_pkg = name.replace("-", "_")
            source_path = f"{dirname}/src/{mod_pkg}/main.py"
            source_code = _fetch_raw(client, source_path) if source_path in all_paths else None
            functions = _parse_functions(source_code) if source_code else []

            # Fetch README (raw)
            readme_path = f"{dirname}/README.md"
            readme = _fetch_raw(client, readme_path) if readme_path in all_paths else ""
            readme = readme or ""

            # Find and fetch examples (raw)
            examples = []
            example_files = _find_example_files(all_paths, dirname)
            for lang, path in example_files:
                content = _fetch_raw(client, path)
                if content:
                    examples.append({
                        "language": lang,
                        "filename": path.split("/")[-1],
                        "code": content,
                    })

            details[name] = {
                **module,
                "readme": readme,
                "functions": functions,
                "examples": examples,
            }

    _cache = {
        "modules": modules,
        "details": details,
        "categories": sorted(categories_seen),
        "ts": time.time(),
    }


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class Dependency(BaseModel):
    name: str
    source: str


class ModuleSummary(BaseModel):
    id: int
    name: str
    description: str
    category: str
    sdk: str
    version: str
    engine_version: str
    dependencies: list[Dependency]
    install_command: str
    github_url: str
    daggerverse_url: str


class FunctionParam(BaseModel):
    name: str
    type: str
    description: str
    required: bool
    default: str


class FunctionInfo(BaseModel):
    name: str
    description: str
    is_check: bool
    is_async: bool
    return_type: str
    params: list[FunctionParam]


class Example(BaseModel):
    language: str
    filename: str
    code: str


class ModuleDetail(ModuleSummary):
    readme: str
    functions: list[FunctionInfo]
    examples: list[Example]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
def health():
    return {"status": "healthy", "service": "module-catalog-api"}


@app.get("/api/categories", response_model=list[str])
def list_categories():
    _refresh_cache()
    return _cache["categories"]


@app.get("/api/items", response_model=list[ModuleSummary])
def list_items():
    _refresh_cache()
    return _cache["modules"]


@app.get("/api/items/{module_name}", response_model=ModuleDetail)
def get_item(module_name: str):
    _refresh_cache()
    module = _cache["details"].get(module_name)
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")
    return module


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
