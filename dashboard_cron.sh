#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2025 Siemens AG

echo "Job start $(date -R)" >> /var/log/sw360/dashboard.log

set -a
source .env
set +a
/home/sw360/.local/bin/sw360-exporter CYS FT SI

echo "Job end   $(date -R)" >> /var/log/sw360/dashboard.log
