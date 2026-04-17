import? 'justfile.local'


[group('test')]
test:
    poetry run pytest -s


[group('run')]
run-ticketmaster-http:
    poetry -C src/ticketmaster run fastapi dev src/ticketmaster/ticketmaster/http/main.py --no-reload --port 8080


[group('infra')]
up-infra:
    docker compose -f docker-compose.yaml -p ticketmaster up -d

[group('infra')]
down-infra:
    docker compose -f docker-compose.yaml -p ticketmaster down

[group('infra')]
restart-infra:
    docker compose -f docker-compose.yaml -p ticketmaster restart
