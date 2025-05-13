#!/bin/bash

if [ -z "$1" ]; then
  echo "Error: version environment variable is not set." >&2
  exit 1
fi

jq '.version = "'"$1"'"' custom_components/wiser_by_feller/manifest.json > tmp
mv tmp custom_components/wiser_by_feller/manifest.json
