from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

EXPECTED_FILES = [
    "README.md",
    "pyproject.toml",
    "app/__init__.py",
    "app/main.py",
    "app/config.py",
    "app/pricing.py",
    "app/routers/__init__.py",
    "app/routers/estimations.py",
    "app/services/__init__.py",
    "app/services/llm_service.py",
    "app/services/llm_wrapper.py",
    "app/services/cache.py",
    "app/context/__init__.py",
    "app/context/examples.py",
]


def test_expected_files_exist():
    missing = [f for f in EXPECTED_FILES if not (ROOT / f).is_file()]
    assert not missing, f"Faltan ficheros/carpetas esperados: {missing}"


def test_every_prompt_version_has_its_templates():
    from app.schemas import PromptVersion

    prompts_dir = ROOT / "app/prompts/estimation"
    missing = [
        f"{v.value}/{name}"
        for v in PromptVersion
        for name in ("system.j2", "user.j2", "examples.j2")
        if not (prompts_dir / v.value / name).is_file()
    ]
    assert not missing, f"Faltan templates para versiones declaradas: {missing}"


def test_app_package_is_importable():
    import app.main  # noqa: F401
    import app.services.llm_service  # noqa: F401
    import app.routers.estimations  # noqa: F401
