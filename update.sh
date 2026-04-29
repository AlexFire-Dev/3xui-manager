#!/bin/bash

docker compose down
docker image rm 3xui-manager-api:latest
git pull
docker compose up -d