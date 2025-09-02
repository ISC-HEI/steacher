#!/bin/bash

# This script is used to initialize the Let's Encrypt certificates.
# It should only be run once.

if ! [ -x "$(command -v docker-compose)" ]; then
  echo 'Error: docker-compose is not installed.' >&2
  exit 1
fi

DOMAIN="steacher.org"
EMAIL="teach@steacher.org"
DATA_PATH="./certbot_data/etc"
RENEWAL_CONFIG_PATH="$DATA_PATH/live/$DOMAIN"

if [ -d "$DATA_PATH" ]; then
  read -p "Existing data found for $DOMAIN. Continue and replace existing certificate? (y/N) " decision
  if [ "$decision" != "Y" ] && [ "$decision" != "y" ]; then
    exit
  fi
fi

if [ -d "$DATA_PATH" ]; then
    # clean up existing data
    rm -rf "$DATA_PATH"
fi

mkdir -p $DATA_PATH

echo "### Creating dummy certificate for $DOMAIN ..."
mkdir -p "$RENEWAL_CONFIG_PATH"
docker-compose run --rm --entrypoint "\
  openssl req -x509 -nodes -newkey rsa:4096 -days 1\
    -keyout '/etc/letsencrypt/live/$DOMAIN/privkey.pem' \
    -out '/etc/letsencrypt/live/$DOMAIN/fullchain.pem' \
    -subj '/CN=localhost'" certbot
echo

echo "### Starting services ..."
docker-compose up -d --build web proxy
echo

echo "### Removing dummy certificate for $DOMAIN ..."
docker-compose run --rm --entrypoint "\
  rm -Rf /etc/letsencrypt/live/$DOMAIN" certbot
echo

echo "### Requesting Let's Encrypt certificate for $DOMAIN ..."
docker-compose run --rm certbot certonly \
  --webroot \
  --webroot-path /app/static \
  -d $DOMAIN \
  --email $EMAIL \
  --agree-tos \
  --no-eff-email \
  --force-renewal
echo

echo "### Restarting Nginx ..."
docker-compose restart proxy
echo

echo "### Done! Your certificates are now set up."
