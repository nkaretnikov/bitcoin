#!/usr/bin/env bash
#
# Copyright (c) The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or https://opensource.org/license/mit.

export LC_ALL=C.UTF-8

set -o errexit -o nounset -o pipefail -o xtrace

export CONTAINER_NAME=ci_native_coverage

export MAKEJOBS=${MAKEJOBS:--j$(if command -v nproc > /dev/null 2>&1; then nproc; else sysctl -n hw.logicalcpu; fi)}
