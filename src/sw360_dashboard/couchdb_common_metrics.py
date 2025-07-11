#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# SPDX-License-Identifier: MIT
# Copyright Siemens AG, 2025. Part of the SW360 Portal Project.
#
# This script is for fetching overall stats for SW360.

import time
from collections import Counter
from collections import defaultdict

from ibm_cloud_sdk_core import ApiException
from ibmcloudant import CloudantV1
from prometheus_client import CollectorRegistry, Gauge, delete_from_gateway

from .couchdb_utils import get_cloudant_client, get_sw360_db_name, \
    get_attachment_db_name, fetch_results, save_new_view, \
    format_for_time_series, push_metrics, query_execution_component_by_type, \
    get_pushgateway_url

# Define Prometheus Gauges for each metric
registry = CollectorRegistry()
projects_count = Gauge(
    'projects_count', 'Total number of projects',
    registry=registry)
releases_count = Gauge(
    'releases_count', 'Total number of releases',
    registry=registry)
components_count_total = Gauge(
    'components_count_total', 'Total number of components',
    registry=registry)
attachment_count = Gauge(
    'attachment_count', 'Total number of attachments',
    registry=registry)

component_type_gauges = {}

Projects = Gauge(
    'Projects', 'Number of projects created per year', ['year'],
    registry=registry)
Components = Gauge(
    'Components', 'Number of components created per year', ['year'],
    registry=registry)
Releases = Gauge(
    'Releases', 'Number of releases created per year', ['year'],
    registry=registry)

release_clearing_status = Gauge(
    "release_clearing_status", "Release status based on type",
    ['type', 'status'], registry=registry)

most_used_component_count = Gauge(
    'most_used_component_count', 'Count of most used components',
    ['componentId', 'Component'], registry=registry)
most_cleared_component_count = Gauge(
    'most_cleared_component_count', 'Count of most cleared components',
    ['componentId', 'Component'], registry=registry)
most_used_license_count = Gauge(
    'most_used_license_count', 'Count of most used licenses',
    ['License'], registry=registry)
unused_component_count = Gauge(
    'unused_component_count', 'Count of components not being used',
    ['component', 'name'], registry=registry)

attachment_usage_department = Gauge(
    'attachment_usage_department', 'Attachment usage by department',
    ['department'], registry=registry)
attachment_usage_group = Gauge(
    'attachment_usage_group', 'Attachment usage by group',
    ['group'], registry=registry)


# --------Common methods---------------
def count_documents_in_view(client: CloudantV1, database: str, design_doc: str,
                            view_name: str) -> int:
    """
    Function to get count of documents/rows in a given view of a design
    document.
    :param client: Cloudant client
    :param database: Name of the database
    :param design_doc: name of design doc
    :param view_name: name of view
    :return: count of documents in the view
    """
    try:
        response = client.post_view(
            db=database, ddoc=design_doc, view=view_name,
            include_docs=False, limit=1).get_result()
    except ApiException as ex:
        print("Error getting count of documents from "
              f"'{design_doc}/{view_name}': {ex}")
        return 0
    return int(response['total_rows'])


# ---------------Counting total number of comp, proj, rel----------------------
def query_execution_count_all(client: CloudantV1, database: str):
    print('\nExecuting the query for counting total number of comp, proj,'
          ' rel.................../')
    data = []

    # Counting total components, projects and releases
    design_doc_arr = {
        "Components": "Component", "Projects": "Project",
        "Releases": "Release"}

    for key, design_doc in design_doc_arr.items():
        item_count = count_documents_in_view(
            client, database, design_doc, "all")
        data.append({"type": key, "value": item_count})

    # Update Prometheus metrics
    for entry in data:
        if entry["type"] == "Projects":
            projects_count.set(entry["value"])
        elif entry["type"] == "Releases":
            releases_count.set(entry["value"])
        elif entry["type"] == "Components":
            components_count_total.set(entry["value"])


# ----------------------Attachment Disk Usage Total----------------------------
def query_execution_attachment_usage_all(client: CloudantV1, database: str):
    print('\nExecuting the query for getting total attachment disk'
          ' usage.................../')
    design_doc = "AttachmentContent"
    view = "totalDiskUsage"
    map_function = {
        "map": "function(doc) {"
               "  if (doc.type === 'attachment' && doc._attachments) {"
               "    for (var key in doc._attachments) {"
               "      emit(doc._id, doc._attachments[key].length);"
               "    }"
               "  }"
               "}", "reduce": "_stats"}

    # Ensure the view is created
    save_new_view(client, database, design_doc, view, map_function)

    # Fetch results from the view
    result = fetch_results(client, database, design_doc, view)

    if not result:
        print("No results found for the view.")
        return

    total_length = 0
    item_count = 0

    for row in result:
        if ('value' in row and 'sum' in row['value'] and 'count'
                in row['value']):
            total_length += row['value']['sum']
            item_count += row['value']['count']

    # Update Prometheus metrics
    attachment_count.set(total_length)


def query_comp_proj_rel_time_series_execution(client: CloudantV1,
                                              database: str):
    print('\nExecuting the time-series query.................../')
    print('\n  Executing the time-series query for projects................./')

    design_doc_arr = {"Component": {"ddoc": "Component", "type": "component"},
                      "Project": {"ddoc": "Project", "type": "project"},
                      "Release": {"ddoc": "Release", "type": "release"}}
    combined_data = {}
    for key, view_info in design_doc_arr.items():
        map_function = {"map": "function(doc) {"
                               f"  if (doc.type == '{view_info['type']}') {{"
                               "    emit(doc.createdOn, doc._id);"
                               "  }"
                               "}"}
        save_new_view(client, database, view_info["ddoc"],
                      "byCreatedOn", map_function)
        result = fetch_results(client, database, view_info["ddoc"],
                               "byCreatedOn")
        if result is None:
            result = []
        data = format_for_time_series(result, key)
        for data_obj in data:
            year = data_obj["Year"]
            if year not in combined_data:
                combined_data[year] = {"Year": year}
            combined_data[year].update(data_obj)

    for year, metrics in combined_data.items():
        Projects.labels(year=year).set(metrics.get("Project", 0))
        Components.labels(year=year).set(metrics.get("Component", 0))
        Releases.labels(year=year).set(metrics.get("Release", 0))


# -------------Cleared/Not Cleared Release status based on Type----------------
def query_execution_releases_ecc_cleared_status(client: CloudantV1,
                                                database: str):
    print('\nExecuting the query for release clearing status................/')
    design_doc = "Release"
    view = "byECCStatus"
    map_function = {'map': """
        function(doc) {
            if (doc.type === 'release' && doc.eccInformation) {
                var eccStatus = doc.eccInformation.eccStatus || 'UNKNOWN';
                var componentType = doc.componentType || 'UNKNOWN';
                emit(doc.componentId, [eccStatus, componentType]);
            }
        }
        """}

    # Creating temporary view byECCStatus for release
    save_new_view(client, database, design_doc, view, map_function)

    # Fetch results from the new view
    result = list(fetch_results(client, database, design_doc, "byECCStatus"))

    if not result:
        print("No results found for the view byECCStatus.")
        return

    # Create a lookup dictionary for component types and statuses
    type_status_count = defaultdict(int)
    for row in result:
        ecc_status, comp_type = row["value"]
        # print(f"ecc_status, comp_type {(ecc_status, comp_type)}")
        comp_type = comp_type or "EMPTY"
        ecc_status = ecc_status or "EMPTY"
        type_status_count[(comp_type, ecc_status)] += 1

    # Update Prometheus metrics
    for (comp_type, status), count in type_status_count.items():
        release_clearing_status.labels(
            type=comp_type, status=status).set(count)


def query_execution_most_used_comp(client: CloudantV1, database: str):
    print('\nExecuting the query for most used components.................../')
    design_doc = "Release"
    view = "byReleaseIdAndComponent"
    map_function = {
        'map': "function(doc) {  if (doc.type == 'release') {"
               "  emit(doc.componentId, doc.name) }}"}

    # Creating temporary view byReleaseIdAndComponent for release
    save_new_view(client, database, design_doc, view, map_function)

    # Fetch results from the new view
    result = list(fetch_results(client, database, design_doc,
                                "byReleaseIdAndComponent"))

    if not result:
        print("No results found for the view byReleaseIdAndComponent.")
        return

    key_counts = {}
    for row in result:
        key = row["key"]
        name = row["value"]
        if key in key_counts:
            key_counts[key]["count"] += 1
        else:
            key_counts[key] = {"key": key, "Component name": name, "count": 1}

    result_list = list(key_counts.values())
    sorted_list = sorted(result_list, key=lambda x: x["count"], reverse=True)

    # Update Prometheus metrics
    for item in sorted_list:
        most_used_component_count.labels(
            componentId=item["key"],
            Component=item["Component name"]).set(item["count"])


def query_execution_most_used_cleared_comp(client: CloudantV1, database: str):
    print('\nExecuting the query for most cleared components................/')
    design_doc = "Release"
    view = "byECCStatusAndName"
    map_function = {'map': """
        function(doc) {
            if (doc.type === 'release' && doc.eccInformation) {
                var eccStatus = doc.eccInformation.eccStatus || 'UNKNOWN';
                var componentName = doc.name || 'UNKNOWN';
                emit(doc.componentId, [eccStatus, componentName]);
            }
        }
        """}

    # Creating temporary view byECCStatus for release
    save_new_view(client, database, design_doc, view, map_function)
    # Fetch results from the new view
    result = list(fetch_results(client, database, design_doc,
                                "byECCStatusAndName"))

    if not result:
        print("No results found for the view byReleaseIdAndComponent.")
        return

    key_counts = {}
    for row in result:
        key = row["key"]
        ecc_status, component_name = row["value"]
        if ecc_status == "APPROVED":
            if key in key_counts:
                key_counts[key]["count"] += 1
            else:
                key_counts[key] = {
                    "key": key, "Component name": component_name, "count": 1}

    result_list = list(key_counts.values())
    sorted_list = sorted(result_list, key=lambda x: x["count"], reverse=True)

    # Update Prometheus metrics
    for item in sorted_list:
        most_cleared_component_count.labels(
            componentId=item["key"], Component=item["Component name"]).set(
            item["count"])


def query_execution_most_used_licenses(client: CloudantV1, database: str):
    print('\nExecuting the query for most used licenses.................../')
    design_doc = "Component"
    view = "bymainLicenseIdArr"
    map_function = {
        'map': "function(doc) { if (doc.type == 'component') {"
               " if(doc.mainLicenseIds) { for(var i in doc.mainLicenseIds){"
               "  emit(doc.mainLicenseIds[i], doc._id); }}"
               " else { emit('EMPTY', doc._id); } } }"}

    # Creating temporary view bymainLicenseIdArr for Component
    save_new_view(client, database, design_doc, view, map_function)

    result = fetch_results(client, database, design_doc, "bymainLicenseIdArr")

    license_count = Counter(item['key'] for item in result)

    sorted_license_list = sorted(license_count.items(), key=lambda x: x[1],
                                 reverse=True)

    # Update Prometheus metrics
    for lic, count in sorted_license_list:
        most_used_license_count.labels(License=lic).set(count)


def query_execution_comp_not_used(client: CloudantV1, database: str):
    print('\nExecuting the query for components not being used............../')

    # Create views to fetch necessary data
    project_design_doc = "Project"
    release_design_doc = "Release"
    project_view = "byReleaseId"
    release_view = "byReleaseIdAndComponentId"

    project_map_function = {
        'map': "function(doc) {  if (doc.type == 'project') {"
               "  emit(doc.releaseId, null) }}"}

    release_map_function = {
        'map': "function(doc) {  if (doc.type == 'release') {"
               "  emit(doc._id, doc.componentId) }}"}

    # Creating temporary views
    save_new_view(client, database, project_design_doc, project_view,
                  project_map_function)
    save_new_view(client, database, release_design_doc, release_view,
                  release_map_function)

    # Fetch results from the views
    proj_rel_results = fetch_results(client, database, project_design_doc,
                                     project_view)
    all_release_results = fetch_results(client, database, release_design_doc,
                                        release_view)

    if proj_rel_results is None or all_release_results is None:
        print("No results found for the views.")
        return

    # Extract release IDs used in projects and all release IDs
    proj_rel_id_list = {row["key"] for row in proj_rel_results}
    rel_id_list = {row["key"] for row in all_release_results}

    # Find unused release IDs
    unused_release_ids = rel_id_list - proj_rel_id_list

    # Filter releases that are not used
    unused_components = [{
        "key": row["value"], "name": row.get("doc", {}).get("name", "N/A")}
        for row in all_release_results if row["key"] in unused_release_ids]

    # Update Prometheus metrics
    for item in unused_components:
        unused_component_count.labels(
            component=item["key"], name=item["name"]).set(1)


def main():
    print("\n Execution starting for exporter ............")
    client = get_cloudant_client()
    sw360_db = get_sw360_db_name()
    attachment_db = get_attachment_db_name()

    # Periodically fetch data and update Prometheus metrics
    query_execution_count_all(client, sw360_db)
    query_execution_attachment_usage_all(client, attachment_db)
    query_execution_component_by_type(
        client, sw360_db, "function(doc) {"
                          " if (doc.type == 'component') {"
                          "  emit(doc.componentType, doc._id);"
                          " }"
                          "}", "bycomponenttype", "...",
        "components_count_total_", component_type_gauges, registry)
    query_comp_proj_rel_time_series_execution(client, sw360_db)
    query_execution_releases_ecc_cleared_status(client, sw360_db)
    query_execution_most_used_comp(client, sw360_db)
    query_execution_most_used_cleared_comp(client, sw360_db)
    query_execution_most_used_licenses(client, sw360_db)
    query_execution_comp_not_used(client, sw360_db)
    print("Code executed")
    delete_from_gateway(get_pushgateway_url(), job='couchdb_exporter',
                        grouping_key={'instance': 'latest'})
    push_metrics('couchdb_exporter', registry)
    print("\n Execution ended for exporter ............")


if __name__ == '__main__':
    try:
        start_time = time.time()
        main()
        print('\nExecution time: ' + "{0:.2f}"
              .format(time.time() - start_time) + 's')

    except Exception as e:
        print('Exception message ', e)
