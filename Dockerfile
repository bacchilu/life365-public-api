FROM python:3.14.7

LABEL maintainer="Luca Bacchi <bacchilu@gmail.com> (https://github.com/bacchilu)"

WORKDIR /app

ARG SUPERCRONIC_VERSION=v0.2.48
ARG TARGETARCH

ARG USER_ID=1000
ARG GROUP_ID=1000
ARG USERNAME=python

RUN groupadd --gid "${GROUP_ID}" "${USERNAME}" \
    && useradd --uid "${USER_ID}" --gid "${GROUP_ID}" --create-home --shell /bin/bash "${USERNAME}" \
    && install -d -o "${USERNAME}" -g "${USERNAME}" /data

COPY requirements-lock.txt ./

RUN pip3 install -r requirements-lock.txt

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends curl ca-certificates; \
    case "${TARGETARCH:-amd64}" in \
      amd64) SUPERCRONIC_ARCH="amd64" ;; \
      arm64) SUPERCRONIC_ARCH="arm64" ;; \
      *) echo "Unsupported TARGETARCH: ${TARGETARCH}"; exit 1 ;; \
    esac; \
    curl -fsSLo /usr/local/bin/supercronic \
      "https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/supercronic-linux-${SUPERCRONIC_ARCH}"; \
    chmod +x /usr/local/bin/supercronic; \
    apt-get purge -y --auto-remove curl; \
    rm -rf /var/lib/apt/lists/*

COPY --chown=${USERNAME}:${USERNAME} app ./app
COPY --chown=${USERNAME}:${USERNAME} crons ./crons

EXPOSE 8000

USER ${USERNAME}

CMD ["fastapi", "run", "app/main.py", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
