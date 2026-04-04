#!/bin/sh
# Ensure upload directories are writable by appuser
# (Needed when Docker volume was previously created with root ownership)
for dir in /code/uploads /code/uploads/evidence /code/uploads/documents /code/uploads/epcis; do
    mkdir -p "$dir"
done

exec "$@"
