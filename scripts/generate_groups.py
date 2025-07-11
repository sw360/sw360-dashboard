#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# SPDX-License-Identifier: EPL-2.0
# Copyright Siemens AG, 2025. Part of the SW360 Portal Project.
#
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# SPDX-License-Identifier: EPL-2.0
#
# This script is for generating group specific scripts.
import argparse
import random
import string
from pathlib import Path

from jinja2 import Environment, FileSystemLoader


def generate_random_string(length=14):
    """Generate random uuid for Grafana dashboard."""
    characters = string.ascii_lowercase
    return ''.join(random.choice(characters) for _ in range(length))


def create_exporter_templates_env():
    template_dir = Path(__file__).parent.parent / 'templates'
    env = Environment(loader=FileSystemLoader(template_dir))
    return env


def create_group_file(env, group_name):
    template = env.get_template('couchdb_DEPT_exporter.py.jinja2')
    group_file_path = Path("src/sw360_dashboard/"
                           f"couchdb_{group_name.lower()}_exporter.py")
    with group_file_path.open("w") as group_file:
        group_file.write(template.render(group=group_name))
        group_file.write("\n")


def update_cli_file(env, groups):
    template = env.get_template('cli.py.jinja2')
    cli_file_path = Path("src/sw360_dashboard/cli.py")
    with cli_file_path.open("w") as cli_file:
        cli_file.write(template.render(groups=groups))
        cli_file.write("\n")


def update_common_file(env, groups):
    template = env.get_template('couchdb_CLI_exporter.py.jinja2')
    common_file_path = Path("src/sw360_dashboard/couchdb_CLI_exporter.py")
    with common_file_path.open("w") as common_file:
        common_file.write(template.render(groups=groups))
        common_file.write("\n")


def create_dashboard_templates_env():
    template_dir = Path(__file__).parent.parent / 'grafana' / 'templates'
    env = Environment(loader=FileSystemLoader(template_dir))
    return env


def create_dashboard_cli_file(env, groups):
    template = env.get_template('cli.json.jinja2')
    cli_file_path = Path("grafana/dashboards/cli.json")
    with cli_file_path.open("w") as cli_file:
        cli_file.write(template.render(groups=groups,
                                       uuid=generate_random_string(14)))


def create_dashboard_file(env, group_name):
    template = env.get_template('dept.json.jinja2')
    group_file = Path(f"grafana/dashboards/{group_name.lower()}.json")
    with group_file.open("w") as dashboard_file:
        dashboard_file.write(template.render(group=group_name,
                                             uuid=generate_random_string(14)))


def copy_common_dashboard_files(env):
    template = env.get_template('global.json.jinja2')
    copy_file_path = Path("grafana/dashboards/global.json")
    with copy_file_path.open("w") as copy_file:
        copy_file.write(template.render(uuid=generate_random_string(14)))


def generate_files(groups):
    exporter_env = create_exporter_templates_env()
    dashboard_env = create_dashboard_templates_env()

    for group in groups:
        create_group_file(exporter_env, group)

    update_cli_file(exporter_env, groups)
    update_common_file(exporter_env, groups)

    create_dashboard_cli_file(dashboard_env, groups)
    for group in groups:
        create_dashboard_file(dashboard_env, group)
    copy_common_dashboard_files(dashboard_env)

    print(f"Group files and CLI updated successfully for groups {groups}.")
    print(f"Dashboard files created successfully for groups {groups}.")


def main():
    parser = argparse.ArgumentParser(description='Generate group scripts.')
    parser.add_argument('groups', type=str,
                        help='Groups to generate scripts for. '
                             'For example DEPTA DEPTB',
                        nargs='+')

    args = parser.parse_args()
    generate_files(args.groups)


if __name__ == "__main__":
    main()
