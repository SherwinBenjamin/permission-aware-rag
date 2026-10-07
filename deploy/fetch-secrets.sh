#!/usr/bin/env sh
# Writes .env from SSM Parameter Store, e.g. /rag/JWT_SECRET -> JWT_SECRET=...
# Requires an instance role allowed ssm:GetParametersByPath and kms:Decrypt.
set -eu
PREFIX="${1:-/rag}"
aws ssm get-parameters-by-path --path "$PREFIX" --with-decryption \
  --query 'Parameters[].[Name,Value]' --output text |
  while IFS="$(printf '\t')" read -r name value; do
    printf '%s=%s\n' "${name##*/}" "$value"
  done > .env
chmod 600 .env
echo "wrote $(wc -l < .env) settings to .env"
