import? 'justfile.local'


[group('test')]
test:
    poetry run pytest -s


[group('run')]
runserver:
    poetry -C src/ticketmaster run fastapi dev src/ticketmaster/ticketmaster/http/main.py --no-reload --port 8080


[group('run')]
[working-directory('frontend')]
runui:
    npm run dev


[group('run')]
[working-directory('frontend')]
build-frontend:
    npm run build


[group('infra')]
up-infra:
    docker compose -f docker-compose.yaml -p ticketmaster up -d

[group('infra')]
down-infra:
    docker compose -f docker-compose.yaml -p ticketmaster down

[group('infra')]
restart-infra:
    docker compose -f docker-compose.yaml -p ticketmaster restart


[group('aws')]
mint-admin-jwt:
    poetry -C src/ticketmaster run python -m ticketmaster.admin.management.commands


[group('aws')]
test-k8s-use-context:
    kubectl config use-context arn:aws:eks:eu-central-1:258167965416:cluster/ticketmaster-test-eu
