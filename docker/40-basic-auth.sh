#!/bin/sh
# Optional password gate for a hosted copy. When SITE_PASSWORD is set, every page and
# /api request needs HTTP basic auth; locally (no SITE_PASSWORD) nothing changes.
# Runs from the nginx image's entrypoint after the template is rendered into conf.d.
set -eu

if [ -n "${SITE_PASSWORD:-}" ]; then
  printf '%s:{PLAIN}%s\n' "${SITE_USER:-judge}" "$SITE_PASSWORD" > /etc/nginx/conf.d/htpasswd
  # Worker processes run as nginx, so the group must be able to read the file.
  chown root:nginx /etc/nginx/conf.d/htpasswd
  chmod 640 /etc/nginx/conf.d/htpasswd
  printf 'auth_basic "Sketch Clash";\nauth_basic_user_file /etc/nginx/conf.d/htpasswd;\n' > /etc/nginx/conf.d/00-basic-auth.conf
  echo "40-basic-auth.sh: password gate enabled for user ${SITE_USER:-judge}"
fi
