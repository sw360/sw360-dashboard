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

import time
import couchdb
import json
import csv
from collections import defaultdict

# ---------------------------------------
# constants
# ---------------------------------------

DRY_RUN = True

COUCHSERVER = "http://admin:sw360fossy12345@localhost:5984/"
DBNAME = 'sw360db'

couch = couchdb.Server(COUCHSERVER)
db = couch[DBNAME]

# ----------------------------------------
# queries
# ----------------------------------------

# Get all components
get_all_components_query = {"selector": {"type": {"$eq": "component"}}, "limit": 999999}

# Get all releases
get_all_releases_query = {"selector": {"type": {"$eq": "release"}}, "limit": 999999}

# Get all projects with releaseIdToUsage field
get_all_projects_query = {"selector": {"type": {"$eq": "project"}}, "limit": 999999}

# ---------------------------------------
# functions
# ---------------------------------------

def get_all_data():
    """Retrieve all components, releases, and projects from the database"""
    print('Fetching all components...')
    components = list(db.find(get_all_components_query))
    print(f'Retrieved {len(components)} components')
    
    print('Fetching all releases...')
    releases = list(db.find(get_all_releases_query))
    print(f'Retrieved {len(releases)} releases')
    
    print('Fetching all projects...')
    projects = list(db.find(get_all_projects_query))
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
                release_project_names[release_id].append({
                    'project_id': project_id,
                    'project_name': project_name
                })
    
    return release_project_count, release_project_names

def organize_data(components, releases, release_project_count, release_project_names, release_to_component):
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
        component_data['releases'].sort(key=lambda x: (-x['project_count'], x['release_name']))
        result.append(component_data)
    
    # Sort components by total releases (descending) and then by name
    result.sort(key=lambda x: (-x['total_releases'], x['component_name']))
    
    return result, orphaned_releases

def generate_reports(organized_data, orphaned_releases):
    """Generate JSON and CSV reports"""
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    
    # Generate JSON report
    json_filename = f'components_releases_projects_report_{timestamp}.json'
    report_data = {
        'generated_on': time.strftime("%Y-%m-%d %H:%M:%S"),
        'total_components': len(organized_data),
        'total_orphaned_releases': len(orphaned_releases),
        'summary': {
            'components_with_releases': len([c for c in organized_data if c['total_releases'] > 0]),
            'components_without_releases': len([c for c in organized_data if c['total_releases'] == 0]),
            'total_releases': sum(c['total_releases'] for c in organized_data),
            'releases_with_projects': sum(1 for c in organized_data for r in c['releases'] if r['project_count'] > 0),
            'releases_without_projects': sum(1 for c in organized_data for r in c['releases'] if r['project_count'] == 0)
        },
        'components': organized_data,
        'orphaned_releases': [
            {
                'release_id': r['_id'],
                'release_name': r.get('name', 'Unknown'),
                'release_version': r.get('version', 'Unknown'),
                'component_id': r.get('componentId', 'Missing')
            } for r in orphaned_releases
        ]
    }
    
    with open(json_filename, 'w') as f:
        json.dump(report_data, f, indent=2, sort_keys=True)
    print(f'JSON report saved to: {json_filename}')
    
    # Generate CSV report
    csv_filename = f'components_releases_projects_summary_{timestamp}.csv'
    with open(csv_filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        
        # Write header
        writer.writerow([
            'Component ID', 'Component Name', 'Component Type',
            'Total Releases', 'Release ID', 'Release Name', 'Release Version',
            'Project Count', 'Project Names', 'Component Created On', 'Component Created By',
            'Release Created On', 'Release Created By'
        ])
        
        # Write data
        for component in organized_data:
            if component['releases']:
                for release in component['releases']:
                    # Join project names with semicolons
                    project_names = "; ".join([p['project_name'] for p in release['projects']])
                    
                    writer.writerow([
                        component['component_id'],
                        component['component_name'],
                        component['component_type'],
                        component['total_releases'],
                        release['release_id'],
                        release['release_name'],
                        release['release_version'],
                        release['project_count'],
                        project_names,
                        component['component_created_on'],
                        component['component_created_by'],
                        release['release_created_on'],
                        release['release_created_by']
                    ])
            else:
                # Component with no releases
                writer.writerow([
                    component['component_id'],
                    component['component_name'],
                    component['component_type'],
                    0,
                    '',
                    '',
                    '',
                    0,
                    '',
                    component['component_created_on'],
                    component['component_created_by'],
                    '',
                    ''
                ])
    
    print(f'CSV report saved to: {csv_filename}')
    
    return json_filename, csv_filename

def print_summary(organized_data, orphaned_releases):
    """Print a summary of the collected data"""
    total_components = len(organized_data)
    total_releases = sum(c['total_releases'] for c in organized_data)
    components_with_releases = len([c for c in organized_data if c['total_releases'] > 0])
    releases_with_projects = sum(1 for c in organized_data for r in c['releases'] if r['project_count'] > 0)
    
    print('\n' + '='*50)
    print('DATA COLLECTION SUMMARY')
    print('='*50)
    print(f'Total Components: {total_components}')
    print(f'Components with Releases: {components_with_releases}')
    print(f'Components without Releases: {total_components - components_with_releases}')
    print(f'Total Releases: {total_releases}')
    print(f'Releases linked to Projects: {releases_with_projects}')
    print(f'Releases not linked to Projects: {total_releases - releases_with_projects}')
    print(f'Orphaned Releases (missing component): {len(orphaned_releases)}')
    
    # Top 10 components by release count
    print('\nTop 10 Components by Release Count:')
    print('-' * 40)
    top_components = sorted(organized_data, key=lambda x: x['total_releases'], reverse=True)[:10]
    for i, comp in enumerate(top_components, 1):
        print(f'{i:2d}. {comp["component_name"]} ({comp["total_releases"]} releases)')
    
    # Top 10 releases by project count
    print('\nTop 10 Releases by Project Count:')
    print('-' * 40)
    all_releases = []
    for comp in organized_data:
        for release in comp['releases']:
            all_releases.append((comp['component_name'], release['release_name'], 
                               release['release_version'], release['project_count']))
    
    top_releases = sorted(all_releases, key=lambda x: x[3], reverse=True)[:10]
    for i, (comp_name, rel_name, version, count) in enumerate(top_releases, 1):
        print(f'{i:2d}. {comp_name} - {rel_name} v{version} ({count} projects)')

def run():
    """Main execution function"""
    start_time = time.time()
    
    print('Starting data collection for components, releases, and projects...')
    
    # Get all data
    components, releases, projects = get_all_data()
    
    # Build mappings
    print('Building release-component mappings...')
    release_to_component = build_release_component_mapping(releases)
    
    # Count projects per release and collect project names
    print('Counting projects per release and collecting project names...')
    release_project_count, release_project_names = count_projects_per_release(projects)
    
    # Organize data
    print('Organizing data by components...')
    organized_data, orphaned_releases = organize_data(
        components, releases, release_project_count, release_project_names, release_to_component
    )
    
    # Generate reports
    print('Generating reports...')
    json_file, csv_file = generate_reports(organized_data, orphaned_releases)
    
    # Print summary
    print_summary(organized_data, orphaned_releases)
    
    execution_time = time.time() - start_time
    print(f'\nData collection completed in {execution_time:.2f} seconds')
    print(f'Reports generated: {json_file}, {csv_file}')

# --------------------------------

if __name__ == "__main__":
    run()
