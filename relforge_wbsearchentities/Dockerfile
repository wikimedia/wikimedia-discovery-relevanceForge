# chosen to have old-enough python (3.7) to use tensorflow 1.x
FROM docker-registry.wikimedia.org/releng/tox-buster:0.5.1

ENV PYTHON=/src/relforge-venv/bin/python
ENV DATASET_DIR=/data

USER root
# Backported ssh for convenience, supports known_hosts.d
RUN apt-get update && apt-get install --yes --no-install-recommends openssh-client/buster-backports python3-virtualenv && \
    groupadd -g 1000 wikian && \
    useradd --create-home --shell /bin/bash --uid 1000 --gid 1000 wikian && \
    mkdir -p "$DATASET_DIR" && chown wikian:wikian "$DATASET_DIR"

ADD --chown=wikian:wikian /reports /src/reports
ADD --chown=wikian:wikian /relforge/ /src/relforge
ADD --chown=wikian:wikian /relforge_wbsearchentities /src/relforge_wbsearchentities
ADD --chown=wikian:wikian /relforge_engine_score/etc/sql /src/relforge_engine_score/etc/sql

USER wikian

RUN python3 -m virtualenv /src/relforge-venv && $PYTHON -m pip install --upgrade pip wheel && \
    $PYTHON -m pip install --editable /src/relforge && \
    $PYTHON -m pip install --editable /src/relforge_wbsearchentities 

WORKDIR /src/relforge_wbsearchentities
# environment-overrides allows PYTHON and DATASET_DIR to be used
ENTRYPOINT ["make", "--environment-overrides", "-f", "Makefile.tf_autocomplete"]
CMD ["DATASET_YEAR=2022", "DATASET_MONTH=3", "report"]
