FROM python:3.14.7

LABEL maintainer="Luca Bacchi <bacchilu@gmail.com> (https://github.com/bacchilu)"

WORKDIR /app

ARG USER_ID=1000
ARG GROUP_ID=1000
ARG USERNAME=python

RUN groupadd --gid "${GROUP_ID}" "${USERNAME}" \
    && useradd --uid "${USER_ID}" --gid "${GROUP_ID}" --create-home --shell /bin/bash "${USERNAME}" \
    && install -d -o "${USERNAME}" -g "${USERNAME}" /data

COPY requirements-lock.txt ./

RUN pip3 install -r requirements-lock.txt

COPY --chown=${USERNAME}:${USERNAME} app ./app

EXPOSE 8000

USER ${USERNAME}

CMD ["fastapi", "run", "app/main.py", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
