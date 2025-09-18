#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# SPDX-License-Identifier: MIT
# Copyright Innomotics, 2025. Part of the SW360 Portal Project.
#
# This script collects data about components, their releases, and the number
# of projects linked to each release. It generates a comprehensive report
# showing:
# - All components
# - Releases linked to each component
# - Number of projects using each release
# -----------------------------------------------------------------------------

from collections import defaultdict

from ibm_cloud_sdk_core import ApiException
from ibmcloudant import CloudantV1
from sw360_dashboard.couchdb_utils import CLOUDANT_LIMIT_MAX

# ----------------------------------------
# queries
# ----------------------------------------

# Get all components
get_all_components_query = {"selector": {"type": {"$eq": "component"}},
                            "limit": 999999}

# Get all releases
get_all_releases_query = {"selector": {"type": {"$eq": "release"}},
                          "limit": 999999}

# Get all projects with releaseIdToUsage field
get_all_projects_query = {"selector": {"type": {"$eq": "project"}},
                          "limit": 999999}


# ---------------------------------------
# functions
# ---------------------------------------

def get_all_data(client: CloudantV1, database: str):
    """Retrieve all components, releases, and projects from the database"""
    components, releases, projects = [], [], []

    print('Fetching all components...')
    try:
        db_query = client.post_find(
            database, get_all_components_query,
            limit=CLOUDANT_LIMIT_MAX,
        ).get_result()
        components = list(db_query["docs"])
    except ApiException as ex:
        print(f"Error: {ex}")
    print(f'Retrieved {len(components)} components')

    print('Fetching all releases...')
    try:
        db_query = client.post_find(
            database, get_all_releases_query,
            limit=CLOUDANT_LIMIT_MAX,
        ).get_result()
        releases = list(db_query["docs"])
    except ApiException as ex:
        print(f"Error: {ex}")
    print(f'Retrieved {len(releases)} releases')

    print('Fetching all projects...')
    try:
        db_query = client.post_find(
            database, get_all_projects_query,
            limit=CLOUDANT_LIMIT_MAX,
        ).get_result()
        projects = list(db_query["docs"])
    except ApiException as ex:
        print(f"Error: {ex}")
    print(f'Retrieved {len(projects)} projects')

    return components, releases, projects


def build_release_component_mapping(releases):
    """Build a mapping from release ID to component ID"""
    release_to_component = {}
    for release in releases:
        release_id = release.get('_id')
        component_id = release.get('componentId')
        if release_id and component_id:
            release_to_component[release_id] = component_id
    return release_to_component


def count_projects_per_release(projects):
    """Count how many projects use each release and collect project names"""
    release_project_count = defaultdict(int)
    release_project_names = defaultdict(list)

    for project in projects:
        project_id = project.get('_id')
        project_name = project.get('name', 'Unknown')

        # Check releaseIdToUsage field
        if 'releaseIdToUsage' in project and project['releaseIdToUsage']:
            for release_id in project['releaseIdToUsage'].keys():
                release_project_count[release_id] += 1
                release_project_names[release_id].append(
                    {'project_id': project_id, 'project_name': project_name}, )

    return release_project_count, release_project_names


def organize_data(components, releases, release_project_count,
                  release_project_names, release_to_component, ):
    """Organize data by component -> releases -> project count"""
    # Create component lookup
    component_lookup = {comp['_id']: comp for comp in components}

    # Group releases by component
    component_releases = defaultdict(list)
    orphaned_releases = []

    for release in releases:
        component_id = release.get('componentId')
        if component_id and component_id in component_lookup:
            component_releases[component_id].append(release)
        else:
            orphaned_releases.append(release)

    # Build final data structure
    result = []

    for component in components:
        component_id = component['_id']
        component_data = {
            'component_id': component_id,
            'component_name': component.get('name', 'Unknown'),
            'component_type': component.get('componentType', 'Unknown'),
            'component_created_on': component.get('createdOn', ''),
            'component_created_by': component.get('createdBy', ''),
            'total_releases': len(component_releases[component_id]),
            'releases': []
        }

        for release in component_releases[component_id]:
            release_id = release['_id']
            project_count = release_project_count.get(release_id, 0)
            projects_list = release_project_names.get(release_id, [])

            release_data = {
                'release_id': release_id,
                'release_name': release.get('name', 'Unknown'),
                'release_version': release.get('version', 'Unknown'),
                'release_created_on': release.get('createdOn', ''),
                'release_created_by': release.get('createdBy', ''),
                'project_count': project_count,
                'projects': projects_list
            }
            component_data['releases'].append(release_data)

        # Sort releases by project count (descending) and then by name
        component_data['releases'].sort(
            key=lambda x: (-x['project_count'], x['release_name']), )
        result.append(component_data)

    # Sort components by total releases (descending) and then by name
    result.sort(key=lambda x: (-x['total_releases'], x['component_name']))

    return result, orphaned_releases
