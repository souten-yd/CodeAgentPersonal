FROM python:3.11-slim

ARG PIP_PACKAGES="fastapi uvicorn requests"
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY scripts/check_environment.py /app/scripts/check_environment.py

RUN python -m pip install --upgrade pip \
    && python -m pip install ${PIP_PACKAGES}

CMD ["python", "scripts/check_environment.py", "--expect-python", "3.11"]
