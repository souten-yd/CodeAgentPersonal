FROM python:3.11-slim

ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY . /app

RUN python -m pip install --upgrade pip \
    && python -m pip install pytest fastapi uvicorn requests pydantic psutil httpx websockets python-multipart

CMD ["python", "-m", "pytest", "-q", "tests/test_project_intelligence_pir14_operational_evidence.py::test_operational_evidence_detects_docker_environment_when_env_set", "tests/test_project_intelligence_pir14_consumer_cutover_gate.py", "tests/test_project_intelligence_pir14_scale_concurrency_evidence.py", "--junitxml", "artifacts/pir14-ci/docker-platform-evidence.xml"]
