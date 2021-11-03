#!/bin/bash

# Delete all containers
docker rm -f $(docker ps -a -q)

# Delete all images
docker rmi -f $(docker images -q)

# Delete volumes and networks
docker volume prune -f
docker network prune -f
