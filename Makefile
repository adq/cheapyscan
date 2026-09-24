# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Andrew de Quincey

# Top-level build for the whole repository.
#
#   make            firmware (build and its tests), host tests, web UI build
#   make firmware   firmware only, see firmware/Makefile
#   make host-test  host application tests, needs uv
#   make web        build the web UI into web/dist, needs npm
#   make web-check  type-check the web UI
#   make run        start the host application
#   make simulate   start it with the simulated board and camera

.PHONY: all firmware host-test web web-check run simulate
.NOTPARALLEL:

all: firmware host-test web

firmware:
	$(MAKE) -C firmware

host-test:
	cd host && uv run pytest -q

web/node_modules: web/package.json web/package-lock.json
	cd web && npm ci
	touch $@

web: web/node_modules
	cd web && npm run build

web-check: web/node_modules
	cd web && npm run check

run: web
	cd host && uv run cheapyscan serve

simulate: web
	cd host && uv run cheapyscan serve --simulate
