#!/usr/bin/env bash
set -euo pipefail
make precommit
make test
