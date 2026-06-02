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
aws-down env="test-eu" profile="tm-test":
    #!/usr/bin/env bash
    set -euo pipefail
    export AWS_PROFILE={{profile}}
    for stack in "ticketmaster-cognito-pre-signup-{{env}}" "frontend-{{env}}" "ticketmaster-{{env}}" "ticketmaster-{{env}}-migrate"; do
        echo "Deleting CloudFormation stack '$stack'..."
        aws cloudformation delete-stack --stack-name "$stack"
        aws cloudformation wait stack-delete-complete --stack-name "$stack"
        echo "Stack '$stack' deleted."
    done
    echo "All ticketmaster stacks for env '{{env}}' deleted. Idle AWS cost should now be ~\$0."
