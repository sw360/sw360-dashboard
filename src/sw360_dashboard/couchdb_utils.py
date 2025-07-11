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
# This utility provides helper functions for connection with cloudant,
# pushgateway, etc.

import os
import time
from collections import defaultdict, Counter
from datetime import datetime

import backoff
import dotenv
import requests.exceptions
from ibm_cloud_sdk_core import ApiException
from ibm_cloud_sdk_core.authenticators import BasicAuthenticator
from ibmcloudant.cloudant_v1 import CloudantV1, DesignDocument, \
    DesignDocumentViewsMapReduce
from prometheus_client import push_to_gateway, CollectorRegistry, Gauge

MAX_BACKOFF_RETRIES = 100
MAX_BACKOFF_TIME = 300
MAX_PUSH_GATEWAY_RETRIES = 5

CLOUDANT_LIMIT_MAX = 4294967295


def get_cloudant_client() -> CloudantV1:
    dotenv.load_dotenv()
    couchdb_password = os.getenv('COUCHDB_PASSWORD', None)
    if couchdb_password is None:
        password_file = os.getenv('COUCHDB_PASSWORD_FILE', None)
        if password_file is None:
            raise ValueError("Need at least one of `COUCHDB_PASSWORD` or "
                             "`COUCHDB_PASSWORD_FILE`")
        with open(password_file, "r") as pass_file:
            couchdb_password = pass_file.read().strip()
    authenticator = BasicAuthenticator(
        username=os.getenv('COUCHDB_USER'), password=couchdb_password)
    client = CloudantV1(authenticator=authenticator)
    client.set_service_url(os.getenv('COUCHDB_HOST'))
    client.configure_service(os.getenv('COUCHDB_HOST'))
    return client


def get_pushgateway_url() -> str:
    dotenv.load_dotenv()
    return os.getenv('PUSHGATEWAY_URL', 'localhost:9091')


def get_database_name() -> str:
    dotenv.load_dotenv()
    return os.getenv('COUCHDB_DATABASE', 'sw360db')


def get_sw360_db_name() -> str:
    return 'sw360db'


def get_attachment_db_name() -> str:
    return 'sw360attachments'


def backoff_printer(details):
    print("Backing off {wait:0.1f} seconds after {tries} tries "
          "calling function {target} with args {args} and kwargs "
          "{kwargs}".format(**details))
    if 'exception' in details:
        print(f"Exception code {details['exception'].status_code} and message "
              f"{details['exception'].message}")


def giveup_printer(details):
    print(f"Server error: {details}")


def giveup_not_timeout_exception(ex: Exception) -> bool:
    """
    Function to give up retrying if the exception is not a timeout exception.
    :param ex: Exception to check
    :return: False if the exception is of timout, True otherwise
    """
    if isinstance(ex, ApiException):
        return 'timeout' not in ex.message
    return True


def giveup_not_indexing_exception(ex: Exception) -> bool:
    """
    Function to give up retrying if the exception is not an indexing wait
    exception.
    :param ex: Exception to check
    :return: False if the exception is of indexing wait, True otherwise
    """
    if isinstance(ex, ApiException):
        return ex.status_code not in [404, 408]
    return True


@backoff.on_exception(backoff.expo, ApiException,
                      max_tries=MAX_BACKOFF_RETRIES,
                      max_time=MAX_BACKOFF_TIME,
                      giveup=giveup_not_timeout_exception,
                      on_backoff=backoff_printer,
                      on_giveup=giveup_printer,
                      raise_on_giveup=False)
def fetch_results(client: CloudantV1, database: str, design_doc: str,
                  view_name: str) -> list | None:
    """
    Get data from a view of a design document.
    :param client: Cloudant client
    :param database: Name of the database
    :param design_doc: Name of the design document
    :param view_name: Name of the view
    :return: List of results from the view
    """
    result = []
    response = client.post_view(database, design_doc, view_name,
                                timeout=1000).get_result()
    if response is not None:
        result = response.get('rows', [])
    return result


@backoff.on_exception(backoff.expo, ApiException,
                      max_tries=MAX_BACKOFF_RETRIES,
                      max_time=MAX_BACKOFF_TIME, on_backoff=backoff_printer,
                      on_giveup=giveup_printer, raise_on_giveup=False)
def create_new_view_in_db(client: CloudantV1, db_name: str, design_doc: str,
                          view: str,
                          map_function: dict[str, str]) -> bool | None:
    try:
        existing_design_doc = client.get_design_document(
            db=db_name, ddoc=design_doc, latest=True).get_result()
    except ApiException:
        existing_design_doc = None
    if existing_design_doc:
        views = {view: DesignDocumentViewsMapReduce(
            map=map_function['map'],
            reduce=map_function.get('reduce', None))}
        for key, value in existing_design_doc.get('views').items():
            views[key] = DesignDocumentViewsMapReduce.from_dict(value)
        design_document = DesignDocument(
            _id=existing_design_doc.get('_id'),
            _rev=existing_design_doc.get('_rev'),
            views=views)
    else:
        design_document = DesignDocument(
            views={
                view: DesignDocumentViewsMapReduce(
                    map=map_function['map'],
                    reduce=map_function.get('reduce', None))})

    response = client.put_design_document(
        db=db_name, design_document=design_document,
        ddoc=design_doc).get_result()
    if response["ok"] is not True:
        raise ApiException(500)
    return True


def save_new_view(client: CloudantV1, db_name: str, design_doc: str, view: str,
                  map_function: dict[str, str]):
    design_exists = False
    view_created = False
    try:
        response = client.get_design_document(db_name, design_doc,
                                              latest=True).get_result()
        if view in response.get('views', {}):
            print(f"View '{view}' already exists in design "
                  f"document '{design_doc}'.")
            design_exists = True
    except Exception:
        pass
    if not design_exists:
        print(f"Creating view '{view}' in design document '{design_doc}'.")
        dotenv.load_dotenv()
        dry_run = os.getenv('DRY_RUN', True)
        dry_run = dry_run is True or dry_run.lower() == "true"
        if not dry_run:
            view_created = True if create_new_view_in_db(
                client, db_name, design_doc, view,
                map_function) is not None else False
        else:
            view_created = True

    if view_created:
        print("Time delay for new view to be processed before accessing it")
        time.sleep(5)
        wait_for_view_indexing(client, db_name, design_doc, view)


@backoff.on_exception(backoff.expo, ApiException,
                      max_tries=MAX_BACKOFF_RETRIES,
                      max_time=MAX_BACKOFF_TIME,
                      giveup=giveup_not_indexing_exception,
                      on_backoff=backoff_printer,
                      on_giveup=giveup_printer,
                      raise_on_giveup=False)
def wait_for_view_indexing(client, db_name, design_doc, view):
    client.post_view(db=db_name, ddoc=design_doc, view=view,
                     limit=1).get_result()


def format_for_time_series(result, doc, key_str="key", value_str="value",
                           year_filter=False):
    upd_result = []
    for item in list(result):
        date_string = item[key_str]
        if date_string:
            try:
                # Ensure date_string follows the expected format
                date_object = datetime.strptime(date_string, "%Y-%m-%d")
                year = date_object.year
                if year_filter and year > 2015:
                    upd_result.append({"key": year, "value": item[value_str]})
                if not year_filter:
                    upd_result.append({"key": year, "value": item[value_str]})
            except ValueError:
                # Handle invalid date formats
                print(f"Invalid date format for entry: {date_string}. "
                      "Skipping this entry.")
                continue
        else:
            # Handle case where 'key' (createdOn date) is None or missing
            print(f"'key' (createdOn) is missing or None for entry: {item}. "
                  "Skipping this entry.")
            continue
    grouped_data = defaultdict(list)

    for entry in upd_result:
        grouped_data[entry["key"]].append(entry["value"])

    data = [{"Year": key, doc: len(values)} for key, values in
            grouped_data.items()]

    return data


@backoff.on_exception(backoff.expo, requests.exceptions.ChunkedEncodingError,
                      max_tries=MAX_PUSH_GATEWAY_RETRIES,
                      on_backoff=backoff_printer, on_giveup=giveup_printer)
def push_metrics(job_name='couchdb_FT_exporter', registry=CollectorRegistry()):
    push_to_gateway(get_pushgateway_url(), job=job_name, registry=registry,
                    grouping_key={'instance': 'latest'})


# Counting total number of comp, proj, rel
def query_execution_count_all(client: CloudantV1, database: str,
                              projects_count: Gauge, releases_count: Gauge,
                              components_count: Gauge, function_def: str,
                              view_name: str):
    print('\nExecuting the query for counting total number of comp, proj,'
          ' rel.....')

    # Counting total projects
    design_doc = "Project"
    map_function = {"map": function_def}
    save_new_view(client, database, design_doc, view_name, map_function)

    result = list(fetch_results(client, database, design_doc, view_name))
    unique_proj = list(set([row['value'] for row in result]))

    data_proj = {"key": "Projects", "value": len(unique_proj)}

    # Counting total releases
    id_list = [row["key"] for row in result]

    try:
        db_query = client.post_find(
            database, {
                "type": "release", "_id": {"$in": id_list}},
            limit=CLOUDANT_LIMIT_MAX).get_result()
        result_rel = list(db_query["docs"])
    except ApiException as ex:
        print(f"Error: {ex}")
        return None, None
    data_rel = {"key": "Releases", "value": len(result_rel)}

    # Counting total components
    id_list = [doc["componentId"] for doc in result_rel]
    try:
        db_query = client.post_find(
            database, {
                "type": "component", "_id": {"$in": id_list}},
            limit=CLOUDANT_LIMIT_MAX).get_result()
        result_comp = list(db_query["docs"])
    except ApiException as ex:
        print(f"Error: {ex}")
        return None, None
    data_comp = {"key": "Components", "value": len(result_comp)}

    length_arr = [data_comp, data_proj, data_rel]

    grouped_data = {}
    for entry in length_arr:
        grouped_data[entry["key"]] = entry["value"]

    # Update Prometheus metrics
    projects_count.set(grouped_data["Projects"])
    releases_count.set(grouped_data["Releases"])
    components_count.set(grouped_data["Components"])

    return result_rel, result_comp


# ---------------Number of Components by Type----------------------------------
def query_execution_component_by_type(client: CloudantV1, database: str,
                                      function_def: str, view_name: str,
                                      tag_name: str, gauge_prefix: str,
                                      component_type_gauges: dict,
                                      registry: CollectorRegistry):
    print('\nExecuting the query for Number of Components by Type'
          f' for {tag_name}...................')
    design_doc = "Component"
    map_function = {"map": function_def}
    # Temporary View
    save_new_view(client, database, design_doc, view_name, map_function)

    result = fetch_results(client, database, design_doc, view_name)

    grouped_data = defaultdict(list)
    for entry in list(result):
        grouped_data[
            "empty" if not entry["key"] or entry["key"].strip() == ""
            else entry["key"]
        ].append(entry["value"])

    for key, values in grouped_data.items():
        gauge_name = f'{gauge_prefix}{key}'
        if key not in component_type_gauges:
            component_type_gauges[key] = Gauge(
                gauge_name, f'Number of components of type {key}',
                registry=registry)
        component_type_gauges[key].set(len(values))


# -----------------Time Series by Year for Proj, Comp, Rel---------------------
def query_comp_proj_rel_time_series_execution(client: CloudantV1,
                                              database: str,
                                              result_rel, result_comp,
                                              function_def: str,
                                              view_name: str,
                                              project_gauge: Gauge,
                                              component_gauge: Gauge,
                                              release_gauge: Gauge):
    print('\nExecuting the time-series query.................../')
    print('\n Executing the time-series query for projects................../')
    design_doc = "Project"
    map_function = {"map": function_def}
    # Temporary View
    save_new_view(client, database, design_doc, view_name, map_function)

    result = list(fetch_results(client, database, design_doc, view_name))
    unique_values = set()
    unique_results = []
    for row in result:
        key = row['key']
        value = row['value']
        if value not in unique_values:
            unique_values.add(value)
            unique_results.append({"key": key, "value": value})
    data_proj = format_for_time_series(
        unique_results, "Project", "key", "value", True)

    # ------------------------ReleaseCreatedOn---------------------------------
    print('\n  Executing the time-series query for release................../')
    data_rel = format_for_time_series(
        list(result_rel), "Release", "createdOn", "_id", True)

    # ---------------------ComponentCreatedOn----------------------------------
    print('\n  Executing the time-series query for component................/')
    data_comp = format_for_time_series(
        list(result_comp), "Component", "createdOn", "_id", True)

    combined_data = {}
    for item in data_proj + data_comp + data_rel:
        year = item["Year"]
        if year not in combined_data:
            combined_data[year] = {"Year": year}
        combined_data[year].update(item)

    for year, metrics in combined_data.items():
        project_gauge.labels(year=year).set(metrics.get("Project", 0))
        component_gauge.labels(year=year).set(metrics.get("Component", 0))
        release_gauge.labels(year=year).set(metrics.get("Release", 0))


# -------------Cleared/Not Cleared Release status based on Type----------------
def query_execution_releases_ecc_cleared_status(result_rel, result_comp,
                                                release_clearing_gauge: Gauge):
    print('\nExecuting the query for release clearing status................/')

    comp_data = [{
        "id": doc["_id"], "componentType": doc.get("componentType")
    } for doc in result_comp]

    comp_lookup = {data["id"]: data for data in comp_data}

    # Merge data from CouchDB into the original documents
    merged_documents = [{
        "id": doc["componentId"],
        "status": None
        if "eccInformation" not in doc
           or "eccStatus" not in doc["eccInformation"]
        else doc["eccInformation"]["eccStatus"],
        "type": comp_lookup[
            doc["componentId"]
        ]["componentType"] if doc["componentId"] in comp_lookup else None
    } for doc in result_rel]

    # Count the occurrences of each type and status combination
    type_status_count = defaultdict(int)
    for doc in merged_documents:
        type_status_count[(
            doc["type"] if doc["type"] else "EMPTY",
            doc["status"] if doc["status"] else "EMPTY")] += 1

    # Update Prometheus metrics
    for (comp_type, status), count in type_status_count.items():
        release_clearing_gauge.labels(type=comp_type,
                                      status=status).set(count)


# ----------------------Most Used Components----------------------------------
def query_execution_most_used_comp(result_rel,
                                   most_used_component_gauge: Gauge):
    print('\n Executing the query for most used components................../')

    key_counts = {}
    for item in result_rel:
        key = item["componentId"]
        name = item["name"]
        if key in key_counts:
            key_counts[key]["count"] += 1
        else:
            key_counts[key] = {"key": key, "Component name": name, "count": 1}

    # Create the new list of dictionaries
    result_list = list(key_counts.values())
    sorted_list = sorted(result_list, key=lambda x: x["count"], reverse=True)

    for item in sorted_list:
        most_used_component_gauge.labels(
            componentId=item["key"],
            Component=item["Component name"]).set(item["count"])


# ------------------Most Used Licenses------------------
def query_execution_most_used_licenses(result_comp,
                                       most_used_license_gauge: Gauge):
    print('\n Executing the query for most used licenses.................../')

    license_list = []
    for doc in result_comp:
        if doc["mainLicenseIds"]:
            for value in doc["mainLicenseIds"]:
                license_list.append(value)

    license_count = Counter(license_list)

    # Update Prometheus metrics
    for license_id, count in license_count.items():
        most_used_license_gauge.labels(License=license_id).set(count)


# --------------------Components that are not used-----------------------------
def query_execution_comp_not_used(client: CloudantV1, database: str,
                                  unused_component_gauge: Gauge):
    print('\n Executing the query for components not being used............./')
    # Create views to fetch necessary data
    project_design_doc = "Project"
    project_view = "byreleaseid"

    project_map_function = {
        'map': "function(doc) {"
               " if (doc.type == 'project') {"
               "  for(var i in doc.releaseIdToUsage) {"
               "   emit(i, doc._id);"
               "  }"
               " }"
               "}"
    }

    save_new_view(client, database, project_design_doc,
                  project_view, project_map_function)

    result = fetch_results(client, database, project_design_doc, project_view)
    if result is None:
        result = []
    proj_rel_id_list = [row["key"] for row in result]

    # Executing the view for all the releases
    # Create views to fetch necessary data
    release_design_doc = "Release"
    release_view = "all"

    project_map_function = {
        'map': "function(doc) {"
               " if (doc.type == 'release') emit(null, doc._id);"
               "}"
    }

    save_new_view(client, database, release_design_doc, release_view,
                  project_map_function)

    result = list(fetch_results(client, database, release_design_doc,
                                release_view))

    rel_id_list = [row["value"] for row in result]

    proj_rel_id_list = set(proj_rel_id_list)
    rel_id_list = set(rel_id_list)

    # Find values in the original list that are not in the input list
    result_id_list = list(rel_id_list - proj_rel_id_list)

    try:
        db_query = client.post_find(
            database, {
                "type": "release", "_id": {"$in": result_id_list}
            }, limit=CLOUDANT_LIMIT_MAX).get_result()
        result_rel = list(db_query["docs"])
    except ApiException as ex:
        print(f"Error: {ex}")
        return None

    comp_result = {}
    for item in result_rel:
        key = item["componentId"]
        name = item["name"]
        comp_result[key] = {"key": key, "name": name}

    result_list = list(comp_result.values())

    # Update Prometheus metrics
    for item in result_list:
        unused_component_gauge.labels(
            component=item["key"], name=item["name"]).set(1)
    return None
