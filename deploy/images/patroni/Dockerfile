FROM postgres:18.6-trixie@sha256:5a5a84b19854a9ffaa54082c166ff4ec27473a361e496e5ea167f298f2da9722

ARG PATRONI_DEB_VERSION=4.1.5-2.pgdg13+1

RUN set -eux; apt-get update; \
    apt-get install -y --no-install-recommends "patroni=${PATRONI_DEB_VERSION}"; \
    rm -rf /var/lib/apt/lists/*; patroni --version

STOPSIGNAL SIGTERM

ENV PGDATA=/var/lib/postgresql/18/main PATRONICTL_CONFIG_FILE=/etc/patroni/patroni.yml

USER 999:999
WORKDIR /var/lib/postgresql
EXPOSE 5432 8008

ENTRYPOINT ["/usr/bin/patroni"]
CMD ["/etc/patroni/patroni.yml"]
