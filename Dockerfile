FROM python:3.14.6

LABEL maintainer="Luca Bacchi <bacchilu@gmail.com> (https://github.com/bacchilu)"

WORKDIR /app

ARG USER_ID=1000
ARG GROUP_ID=1000
ARG USERNAME=python

RUN groupadd --gid "${GROUP_ID}" "${USERNAME}" && useradd --uid "${USER_ID}" --gid "${GROUP_ID}" --create-home --shell /bin/bash "${USERNAME}"

COPY requirements-lock.txt ./

RUN pip3 install -r requirements-lock.txt

COPY --chown=${USERNAME}:${USERNAME} app ./app

EXPOSE 8000

USER ${USERNAME}

# Keep one worker while token sessions are stored in process-local memory.
CMD ["fastapi", "run", "app/main.py", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
