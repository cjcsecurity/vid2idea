#!/bin/sh
set -eu

# An attached Windows wsl.exe process keeps WSL alive. Systemd alone does not.
systemctl --user start vid2idea
exec sleep infinity
