#!/bin/sh
# Start the phone tunnels, or print every useful link of the running stack.
# The stack is chosen by the Makefile through COMPOSE_FILE (dev or prod files + tunnel file).
#   tunnel.sh start   tunnels first, then Metro with both public URLs
#   tunnel.sh links   local URLs, plus the public ones if the tunnels run
set -eu

dc() { docker compose "$@"; }

running() { [ -n "$(dc ps -q --status running "$1" 2>/dev/null)" ]; }

# Latest quick-tunnel URL in a container's logs (cloudflared prints it at startup).
url() {
	for _ in $(seq 1 30); do
		u=$(dc logs "$1" 2>&1 | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -1)
		if [ -n "$u" ]; then echo "$u"; return 0; fi
		sleep 1
	done
	return 1
}

start() {
	dc up -d tunnel metro-tunnel
	api=$(url tunnel) && metro=$(url metro-tunnel) || {
		echo "No tunnel URL after 30 s, check: docker compose logs tunnel metro-tunnel" >&2
		exit 1
	}
	# Expo Go speaks plain HTTP to the dev server: exp://host:80 (Expo CLI docs example).
	EXPO_PUBLIC_API_URL=$api EXPO_PACKAGER_PROXY_URL=http://${metro#https://} \
		dc up -d --force-recreate metro
}

links() {
	echo
	echo "On this PC:"
	echo "  Swagger      http://localhost:8000/docs"
	if running mailpit; then echo "  Mailpit      http://localhost:8025"; fi
	if running grafana; then echo "  Grafana      http://localhost:3000   (admin / GRAFANA_ADMIN_PASSWORD, default: admin)"; fi
	if running prometheus; then echo "  Prometheus   http://localhost:9090"; fi
	if running tunnel; then
		echo "On the phone (public, new URLs on every tunnel start):"
		echo "  API          $(url tunnel)"
		# metro-tunnel, not metro: metro was just recreated and may not report "running" yet.
		if running metro-tunnel; then
			metro=$(url metro-tunnel)
			echo "  Expo Go      exp://${metro#https://}:80   (first load bundles the app: ~1 min)"
		fi
	fi
	echo
}

case "${1:-}" in
start) start ;;
links) links ;;
*) echo "usage: tunnel.sh start|links" >&2; exit 2 ;;
esac
