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


[group('aws')]
aws-down stack="hello-test" profile="tm-test":
    #!/usr/bin/env bash
    set -euo pipefail
    export AWS_PROFILE={{profile}}
    echo "Deleting CloudFormation stack '{{stack}}' (ALB + NAT + ECS + task defs)..."
    aws cloudformation delete-stack --stack-name {{stack}}
    aws cloudformation wait stack-delete-complete --stack-name {{stack}}
    echo "Stack '{{stack}}' deleted. Idle AWS cost should now be ~\$0."
