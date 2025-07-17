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
# This module contains utility functions for AWS CloudWatch integration,
# EC2 instance monitoring, and EBS volume metrics collection.

import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import backoff
import boto3
import dotenv
import requests.exceptions
from botocore.exceptions import ClientError, NoCredentialsError
from prometheus_client import push_to_gateway, CollectorRegistry, Gauge

# Load environment variables from .env file
dotenv.load_dotenv()

MAX_BACKOFF_RETRIES = 5
MAX_BACKOFF_TIME = 60
MAX_PUSH_GATEWAY_RETRIES = 5


def get_aws_session():
    """
    Create AWS session using environment variables or IAM role
    """
    # Try to get credentials from environment variables first
    aws_access_key = os.getenv('AWS_ACCESS_KEY_ID')
    aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
    aws_session_token = os.getenv('AWS_SESSION_TOKEN')  # For temporary credentials
    aws_region = os.getenv('AWS_DEFAULT_REGION', 'eu-central-1')
    
    if aws_access_key and aws_secret_key:
        session = boto3.Session(
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key,
            aws_session_token=aws_session_token,  # Will be None for permanent credentials
            region_name=aws_region
        )
    else:
        # Fall back to IAM role or default credential chain
        session = boto3.Session(region_name=aws_region)
    
    return session


def get_cloudwatch_client():
    """
    Get CloudWatch client
    """
    session = get_aws_session()
    return session.client('cloudwatch')


def get_ec2_client():
    """
    Get EC2 client
    """
    session = get_aws_session()
    return session.client('ec2')


def get_pushgateway_url() -> str:
    """
    Get Push Gateway URL from environment
    """
    return os.getenv('PUSHGATEWAY_URL', 'localhost:9091')


def backoff_printer(details):
    print("Backing off {wait:0.1f} seconds after {tries} tries "
          "calling function {target} with args {args} and kwargs "
          "{kwargs}".format(**details))
    if 'exception' in details:
        print(f"Exception: {details['exception']}")


def giveup_printer(details):
    print(f"AWS API error: {details}")


def giveup_not_throttle_exception(ex: Exception) -> bool:
    """
    Function to give up retrying if the exception is not a throttle exception.
    """
    if isinstance(ex, ClientError):
        error_code = ex.response.get('Error', {}).get('Code', '')
        return error_code not in ['Throttling', 'RequestLimitExceeded', 'ServiceUnavailable']
    return True


@backoff.on_exception(backoff.expo, ClientError, max_tries=MAX_BACKOFF_RETRIES, max_time=MAX_BACKOFF_TIME,
                      giveup=giveup_not_throttle_exception, on_backoff=backoff_printer, on_giveup=giveup_printer,
                      raise_on_giveup=False)
def get_running_instances(ec2_client) -> List[Dict]:
    """
    Get all running EC2 instances
    """
    try:
        response = ec2_client.describe_instances(
            Filters=[
                {
                    'Name': 'instance-state-name',
                    'Values': ['running']
                }
            ]
        )
        
        instances = []
        for reservation in response['Reservations']:
            for instance in reservation['Instances']:
                instance_info = {
                    'InstanceId': instance['InstanceId'],
                    'InstanceType': instance['InstanceType'],
                    'LaunchTime': instance['LaunchTime'],
                    'AvailabilityZone': instance['Placement']['AvailabilityZone'],
                    'Tags': {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])}
                }
                instances.append(instance_info)
        
        return instances
    except Exception as e:
        print(f"Error fetching running instances: {e}")
        return []


@backoff.on_exception(backoff.expo, ClientError, max_tries=MAX_BACKOFF_RETRIES, max_time=MAX_BACKOFF_TIME,
                      giveup=giveup_not_throttle_exception, on_backoff=backoff_printer, on_giveup=giveup_printer,
                      raise_on_giveup=False)
def get_cloudwatch_metric(cloudwatch_client, namespace: str, metric_name: str, dimensions: List[Dict], 
                         start_time: datetime, end_time: datetime, statistic: str = 'Average') -> Optional[float]:
    """
    Get CloudWatch metric data
    """
    try:
        response = cloudwatch_client.get_metric_statistics(
            Namespace=namespace,
            MetricName=metric_name,
            Dimensions=dimensions,
            StartTime=start_time,
            EndTime=end_time,
            Period=300,  # 5 minutes
            Statistics=[statistic]
        )
        
        if response['Datapoints']:
            # Get the latest datapoint
            latest_datapoint = max(response['Datapoints'], key=lambda x: x['Timestamp'])
            return latest_datapoint[statistic]
        
        return None
    except Exception as e:
        print(f"Error fetching CloudWatch metric {metric_name}: {e}")
        return None


def get_ebs_volumes_for_instance(ec2_client, instance_id: str) -> List[Dict]:
    """
    Get EBS volumes attached to an instance
    """
    try:
        response = ec2_client.describe_volumes(
            Filters=[
                {
                    'Name': 'attachment.instance-id',
                    'Values': [instance_id]
                }
            ]
        )
        
        volumes = []
        for volume in response['Volumes']:
            # Only include volumes that are attached
            if volume['State'] == 'in-use':
                volume_info = {
                    'VolumeId': volume['VolumeId'],
                    'VolumeType': volume['VolumeType'],
                    'Size': volume['Size'],  # Size in GB
                    'State': volume['State'],
                    'AvailabilityZone': volume['AvailabilityZone']
                }
                volumes.append(volume_info)
        
        return volumes
    except Exception as e:
        print(f"Error fetching EBS volumes for instance {instance_id}: {e}")
        return []


@backoff.on_exception(backoff.expo, requests.exceptions.ChunkedEncodingError, max_tries=MAX_PUSH_GATEWAY_RETRIES,
                      on_backoff=backoff_printer, on_giveup=giveup_printer)
def push_metrics(job_name='aws_cloudwatch_exporter', registry=CollectorRegistry()):
    """
    Push metrics to Prometheus Push Gateway
    """
    push_to_gateway(get_pushgateway_url(), job=job_name, registry=registry, grouping_key={'instance': 'latest'})


def collect_ec2_instance_metrics(ec2_client, cloudwatch_client, instances: List[Dict], 
                                running_instances_gauge: Gauge, cpu_utilization_gauge: Gauge,
                                memory_utilization_gauge: Gauge, network_in_gauge: Gauge,
                                network_out_gauge: Gauge):
    """
    Collect EC2 instance metrics and update gauges
    """
    print("Collecting EC2 instance metrics...")
    
    # Set total running instances count
    running_instances_gauge.set(len(instances))
    
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(minutes=15)  # Last 15 minutes
    
    processed_instances = set()  # Track processed instances to avoid duplicates
    
    for instance in instances:
        instance_id = instance['InstanceId']
        
        # Skip if instance already processed (avoid duplicates)
        if instance_id in processed_instances:
            print(f"Skipping duplicate instance: {instance_id}")
            continue
            
        processed_instances.add(instance_id)
        instance_type = instance['InstanceType']
        az = instance['AvailabilityZone']
        name = instance['Tags'].get('Name', 'unnamed')
        
        print(f"Processing instance: {instance_id} ({name})")
        
        dimensions = [{'Name': 'InstanceId', 'Value': instance_id}]
        
        # CPU Utilization
        cpu_util = get_cloudwatch_metric(
            cloudwatch_client, 'AWS/EC2', 'CPUUtilization', 
            dimensions, start_time, end_time, 'Average'
        )
        if cpu_util is not None:
            cpu_utilization_gauge.labels(
                instance_id=instance_id, 
                instance_type=instance_type,
                availability_zone=az,
                name=name
            ).set(cpu_util)
        
        # Memory Utilization (requires CloudWatch agent)
        memory_util = get_cloudwatch_metric(
            cloudwatch_client, 'CWAgent', 'mem_used_percent',
            dimensions, start_time, end_time, 'Average'
        )
        if memory_util is not None:
            memory_utilization_gauge.labels(
                instance_id=instance_id,
                instance_type=instance_type,
                availability_zone=az,
                name=name
            ).set(memory_util)
        
        # Network In
        network_in = get_cloudwatch_metric(
            cloudwatch_client, 'AWS/EC2', 'NetworkIn',
            dimensions, start_time, end_time, 'Average'
        )
        if network_in is not None:
            network_in_gauge.labels(
                instance_id=instance_id,
                instance_type=instance_type,
                availability_zone=az,
                name=name
            ).set(network_in)
        
        # Network Out
        network_out = get_cloudwatch_metric(
            cloudwatch_client, 'AWS/EC2', 'NetworkOut',
            dimensions, start_time, end_time, 'Average'
        )
        if network_out is not None:
            network_out_gauge.labels(
                instance_id=instance_id,
                instance_type=instance_type,
                availability_zone=az,
                name=name
            ).set(network_out)


def collect_ebs_volume_metrics(ec2_client, cloudwatch_client, instances: List[Dict],
                              volume_size_gauge: Gauge, volume_used_size_gauge: Gauge, 
                              volume_free_size_gauge: Gauge, volume_utilization_percent_gauge: Gauge,
                              volume_iops_gauge: Gauge, volume_read_ops_gauge: Gauge, volume_write_ops_gauge: Gauge):
    """
    Collect EBS volume metrics and update gauges
    """
    print("Collecting EBS volume metrics")
    
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(minutes=15)  # Last 15 minutes
    
    processed_volumes = set()  # Track processed volumes to avoid duplicates
    
    for instance in instances:
        instance_id = instance['InstanceId']
        instance_name = instance['Tags'].get('Name', 'unnamed')
        
        print(f"Processing EBS volumes for instance: {instance_id} ({instance_name})")
        
        try:
            disk_details = get_enhanced_disk_metrics(ec2_client, cloudwatch_client, instance_id)
            
            if not disk_details:
                print(f"No disk metrics found for instance {instance_id}, falling back to basic volume info")
                # Fallback to basic volume information
                volumes = get_ebs_volumes_for_instance(ec2_client, instance_id)
                
                for volume in volumes:
                    volume_id = volume['VolumeId']
                    if volume_id in processed_volumes:
                        continue
                    
                    processed_volumes.add(volume_id)
                    volume_type = volume['VolumeType']
                    volume_size = volume['Size']
                    
                    # Set basic volume info
                    volume_size_gauge.labels(
                        volume_id=volume_id,
                        instance_id=instance_id,
                        instance_name=instance_name,
                        volume_type=volume_type
                    ).set(volume_size)
                    
                    # Set estimated values (50% utilization)
                    estimated_used_gb = volume_size * 0.5
                    estimated_free_gb = volume_size - estimated_used_gb
                    estimated_utilization = 50.0
                    
                    volume_used_size_gauge.labels(
                        volume_id=volume_id,
                        instance_id=instance_id,
                        instance_name=instance_name,
                        volume_type=volume_type
                    ).set(estimated_used_gb)
                    
                    volume_free_size_gauge.labels(
                        volume_id=volume_id,
                        instance_id=instance_id,
                        instance_name=instance_name,
                        volume_type=volume_type
                    ).set(estimated_free_gb)
                    
                    volume_utilization_percent_gauge.labels(
                        volume_id=volume_id,
                        instance_id=instance_id,
                        instance_name=instance_name,
                        volume_type=volume_type
                    ).set(estimated_utilization)
                continue
            
            # Process enhanced disk metrics
            for device, metrics in disk_details.items():
                volume_id = metrics['volume_id']
                
                # Skip if volume already processed (avoid duplicates)
                if volume_id in processed_volumes:
                    print(f"Skipping duplicate volume: {volume_id}")
                    continue
                
                processed_volumes.add(volume_id)
                volume_type = metrics['volume_type']
                volume_size = metrics['volume_size']
                
                print(f"Processing volume: {volume_id} (device: {device}) for instance {instance_id}")
                
                # Set volume size
                volume_size_gauge.labels(
                    volume_id=volume_id,
                    instance_id=instance_id,
                    instance_name=instance_name,
                    volume_type=volume_type
                ).set(volume_size)
                
                volume_used_size_gauge.labels(
                    volume_id=volume_id,
                    instance_id=instance_id,
                    instance_name=instance_name,
                    volume_type=volume_type
                ).set(metrics['used_gb'])
                
                volume_free_size_gauge.labels(
                    volume_id=volume_id,
                    instance_id=instance_id,
                    instance_name=instance_name,
                    volume_type=volume_type
                ).set(metrics['free_gb'])
                
                volume_utilization_percent_gauge.labels(
                    volume_id=volume_id,
                    instance_id=instance_id,
                    instance_name=instance_name,
                    volume_type=volume_type
                ).set(metrics['utilization_percent'])
                
                print(f"Volume {volume_id}: {metrics['used_gb']:.2f}GB used, "
                      f"{metrics['free_gb']:.2f}GB free, {metrics['utilization_percent']:.1f}% utilization")
            
            # Collect additional EBS metrics (IOPS, read/write ops) for all volumes
            volumes = get_ebs_volumes_for_instance(ec2_client, instance_id)
            for volume in volumes:
                volume_id = volume['VolumeId']
                volume_type = volume['VolumeType']
                
                dimensions = [{'Name': 'VolumeId', 'Value': volume_id}]
                
                # Volume IOPS (Queue Length)
                volume_iops = get_cloudwatch_metric(
                    cloudwatch_client, 'AWS/EBS', 'VolumeQueueLength',
                    dimensions, start_time, end_time, 'Average'
                )
                if volume_iops is not None:
                    volume_iops_gauge.labels(
                        volume_id=volume_id,
                        instance_id=instance_id,
                        instance_name=instance_name,
                        volume_type=volume_type
                    ).set(volume_iops)
                
                # Volume Read Operations
                volume_read_ops = get_cloudwatch_metric(
                    cloudwatch_client, 'AWS/EBS', 'VolumeReadOps',
                    dimensions, start_time, end_time, 'Sum'
                )
                if volume_read_ops is not None:
                    volume_read_ops_gauge.labels(
                        volume_id=volume_id,
                        instance_id=instance_id,
                        instance_name=instance_name,
                        volume_type=volume_type
                    ).set(volume_read_ops)
                
                # Volume Write Operations
                volume_write_ops = get_cloudwatch_metric(
                    cloudwatch_client, 'AWS/EBS', 'VolumeWriteOps',
                    dimensions, start_time, end_time, 'Sum'
                )
                if volume_write_ops is not None:
                    volume_write_ops_gauge.labels(
                        volume_id=volume_id,
                        instance_id=instance_id,
                        instance_name=instance_name,
                        volume_type=volume_type
                    ).set(volume_write_ops)
                    
        except Exception as e:
            print(f"Error collecting EBS metrics for instance {instance_id}: {e}")
            continue


def get_size_gb(size_bytes: int) -> float:
    """Convert bytes to GB"""
    return size_bytes / (1024 * 1024 * 1024)


def get_metric_data_enhanced(cloudwatch_client, today_obj: datetime, 
                           yesterday_obj: datetime, instance_id: str):
    """
    Enhanced method to get disk metrics using batch queries
    """
    # Get disk total metrics
    disk_total_metrics = cloudwatch_client.list_metrics(
        Namespace='CWAgent', 
        MetricName='disk_total',
        Dimensions=[
            {
                'Name': 'InstanceId',
                'Value': instance_id
            },
        ]
    )
    
    # Get disk used metrics  
    disk_used_metrics = cloudwatch_client.list_metrics(
        Namespace='CWAgent', 
        MetricName='disk_used',
        Dimensions=[
            {
                'Name': 'InstanceId',
                'Value': instance_id
            },
        ]
    )
    
    metric_query = []
    device_names = set()
    
    # Add disk total metrics to query
    metric_query, dev_set = add_dev_to_query(disk_total_metrics, metric_query, "disk_total")
    device_names |= dev_set
    
    # Add disk used metrics to query
    metric_query, dev_set = add_dev_to_query(disk_used_metrics, metric_query, "disk_used")
    device_names |= dev_set
    
    if len(metric_query) < 1:
        return None, device_names
    
    # Execute batch query
    response = cloudwatch_client.get_metric_data(
        MetricDataQueries=metric_query,
        StartTime=yesterday_obj,
        EndTime=today_obj
    )
    
    return response, device_names


def add_dev_to_query(disk_metrics, metric_query, metric_name):
    """
    Add device metrics to the batch query
    """
    devices = set()
    for metric in disk_metrics['Metrics']:
        dev_name = [d for d in metric['Dimensions'] if d['Name'] == 'device'][0]['Value']
        devices.add(dev_name)
        metric_query.append({
            "Id": f"{metric_name}_{dev_name}",
            "MetricStat": {
                "Metric": metric,
                "Period": 86400,
                "Stat": "Maximum"
            },
            "ReturnData": True
        })
    return metric_query, devices


def find_closest_volume(volume_size: float, volumes_response: dict):
    """
    Find the closest volume by size to match disk metrics to actual volumes
    """
    closest_vol = None
    closest_diff = float('inf')
    
    for vol in volumes_response['Volumes']:
        diff = vol['Size'] - volume_size
        if 0 <= diff < closest_diff:
            closest_vol = vol
            closest_diff = diff
    
    return closest_vol


def get_enhanced_disk_metrics(ec2_client, cloudwatch_client, instance_id: str):
    """
    Returns structured data with volume mapping
    """
    today_obj = datetime.utcnow()
    yesterday_obj = today_obj - timedelta(days=1)
    
    # Get metric data using enhanced approach
    response, device_names = get_metric_data_enhanced(
        cloudwatch_client, today_obj, yesterday_obj, instance_id
    )
    
    if not response or len(device_names) < 1:
        return {}
    
    # Get volumes for this instance
    volumes_response = ec2_client.describe_volumes(
        Filters=[
            {
                'Name': 'attachment.instance-id',
                'Values': [instance_id]
            }
        ]
    )
    
    disk_details = {}
    
    for device in device_names:
        total_size = -1
        used_size = -1
        
        if response['MetricDataResults']:
            for result in response['MetricDataResults']:
                if result['Id'] == f'disk_total_{device}' and result['Values']:
                    total_size = int(max(result['Values']))
                if result['Id'] == f'disk_used_{device}' and result['Values']:
                    used_size = int(max(result['Values']))
        
        if total_size > 0:
            total_size_gb = get_size_gb(total_size)
            used_size_gb = get_size_gb(used_size) if used_size > 0 else 0
            free_size_gb = get_size_gb(total_size - used_size) if used_size > 0 else total_size_gb
            
            # Find matching volume
            vol = find_closest_volume(total_size_gb, volumes_response)
            
            if vol:
                disk_details[device] = {
                    'total_bytes': total_size,
                    'used_bytes': used_size,
                    'free_bytes': total_size - used_size,
                    'total_gb': total_size_gb,
                    'used_gb': used_size_gb,
                    'free_gb': free_size_gb,
                    'utilization_percent': (used_size_gb / total_size_gb * 100) if total_size_gb > 0 else 0,
                    'device': device,
                    'volume_id': vol['VolumeId'],
                    'volume_size': vol['Size'],
                    'volume_type': vol['VolumeType'],
                    'volume_state': vol['State']
                }
    
    return disk_details
