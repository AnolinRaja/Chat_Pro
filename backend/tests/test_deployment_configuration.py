from pathlib import Path
import re


BACKEND_DIR = Path(__file__).parents[1]
DOCKERFILE = BACKEND_DIR / "Dockerfile"
DOCKERIGNORE = BACKEND_DIR / ".dockerignore"
README = BACKEND_DIR.parent / "README.md"


def test_dockerfile_uses_single_production_uvicorn_worker():
    dockerfile = DOCKERFILE.read_text()

    assert "FROM python:3.13-slim" in dockerfile
    assert "--host 0.0.0.0" in dockerfile
    assert "--workers 1" in dockerfile
    assert "--reload" not in dockerfile
    assert "pip install --no-cache-dir -r requirements.txt" in dockerfile


def test_dockerfile_healthcheck_uses_valid_cmd_syntax():
    dockerfile = DOCKERFILE.read_text()

    # HEALTHCHECK must use CMD format (not CMD-SHELL which is invalid)
    assert "HEALTHCHECK" in dockerfile
    assert "CMD-SHELL" not in dockerfile
    assert 'CMD ["python"' in dockerfile
    assert "/health" in dockerfile
    assert "timeout=10" in dockerfile


def test_dockerfile_healthcheck_uses_liveness_endpoint():
    dockerfile = DOCKERFILE.read_text()

    assert "HEALTHCHECK" in dockerfile
    assert "/health" in dockerfile
    assert "127.0.0.1" in dockerfile


def test_docker_healthcheck_timeout_exceeds_mongodb_timeout():
    dockerfile = DOCKERFILE.read_text()
    database = (BACKEND_DIR / "app" / "db.py").read_text()

    healthcheck_timeout = int(re.search(r"--timeout=(\d+)s", dockerfile).group(1))
    mongodb_timeout = int(re.search(r"serverSelectionTimeoutMS=(\d+)", database).group(1)) / 1000

    assert healthcheck_timeout > mongodb_timeout


def test_embedded_healthcheck_timeout_is_within_docker_timeout():
    dockerfile = DOCKERFILE.read_text()
    docker_timeout = int(re.search(r"--timeout=(\d+)s", dockerfile).group(1))
    http_timeout = int(re.search(r"urlopen\([^\n]+timeout=(\d+)\)", dockerfile).group(1))

    assert http_timeout > 5
    assert http_timeout <= docker_timeout


def test_dockerignore_excludes_secrets_and_local_artifacts():
    dockerignore = DOCKERIGNORE.read_text().splitlines()

    for entry in [".env", ".env.*", ".git", ".venv", "__pycache__", ".pytest_cache", "tests"]:
        assert entry in dockerignore


def test_readme_documents_container_runtime_requirements():
    readme = README.read_text()

    for text in [
        "docker build -f backend/Dockerfile -t chatpro-backend backend",
        "MONGODB_URI",
        "MONGODB_DB",
        "JWT_SECRET_KEY",
        "/health",
        "/ready",
        "one application process",
        "external MongoDB",
    ]:
        assert text in readme
