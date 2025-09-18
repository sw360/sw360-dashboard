<!--
 SPDX-License-Identifier: MIT
 SPDX-FileCopyrightText: 2025 Siemens AG
-->
# AWS CloudWatch Exporter

This exporter collects AWS EC2 and EBS metrics from CloudWatch and pushes them to Prometheus Push Gateway for visualization in Grafana.

## Features

The AWS CloudWatch Exporter provides the following metrics:

### EC2 Instance Metrics
- **Total Running Instances**: Count of all running EC2 instances
- **CPU Utilization**: CPU usage percentage per instance
- **Memory Utilization**: Memory usage percentage (requires CloudWatch agent)
- **Network In/Out**: Network traffic in bytes
- **Instance Distribution**: Count by instance type and availability zone

### EBS Volume Metrics
- **Volume Size**: Size of each EBS volume in GB
- **Volume IOPS**: Queue length (indicator of IOPS)
- **Read/Write Operations**: Volume read and write operations
- **Disk Utilization**: Real-time disk space utilization percentage
- **Free Space**: Available disk space in bytes and GB
- **Used Space**: Used disk space in bytes and GB
- **Device Mapping**: Automatic mapping of disk metrics to EBS volumes

## Prerequisites

### AWS Credentials
You need to configure AWS credentials in one of the following ways:

1. **Environment Variables** (Recommended for development):
   ```bash
   export AWS_ACCESS_KEY_ID=your_access_key
   export AWS_SECRET_ACCESS_KEY=your_secret_key
   export AWS_DEFAULT_REGION=us-east-1
   ```

2. **IAM Role** (Recommended for production on EC2):
   - Attach an IAM role to your EC2 instance with the required permissions

3. **AWS Credentials File**:
   - Configure `~/.aws/credentials` file

### Required AWS Permissions
The AWS user/role needs the following permissions:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "ec2:DescribeInstances",
                "ec2:DescribeRegions",
                "ec2:DescribeVolumes",
                "cloudwatch:GetMetricStatistics"
            ],
            "Resource": "*"
        }
    ]
}
```

### CloudWatch Agent
For advanced metrics (memory and disk utilization), install and configure the CloudWatch agent on your EC2 instances:

```bash
# Install CloudWatch agent on EC2 instances
sudo yum install amazon-cloudwatch-agent

# Configure to publish disk and memory metrics
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-config-wizard
```

The exporter will automatically collect these metrics when available:
- `CWAgent.disk_total` - Total disk space
- `CWAgent.disk_used` - Used disk space
- `CWAgent.memory_utilization` - Memory utilization

If CloudWatch agent metrics are not available, the exporter will fall back to basic EBS volume information.

## Configuration

### Environment Variables
- `AWS_ACCESS_KEY_ID`: AWS access key (optional if using IAM role)
- `AWS_SECRET_ACCESS_KEY`: AWS secret key (optional if using IAM role)
- `AWS_DEFAULT_REGION`: AWS region (default: us-east-1)
- `PUSHGATEWAY_URL`: Prometheus Push Gateway URL (default: localhost:9091)

## Installation

1. Install dependencies:
   ```bash
   pip install boto3 prometheus-client requests backoff
   ```

2. Or use Poetry:
   ```bash
   poetry install
   ```

## Usage

### Run the AWS Exporter
```bash
# Using the CLI
python -m sw360_dashboard.cli AWS

# Or run directly
python -m sw360_dashboard.aws_cloudwatch_exporter
```

### Schedule with Cron
Add to your crontab to run every 5 minutes:
```bash
*/5 * * * * /usr/bin/python3 /path/to/dashboard/src/sw360_dashboard/aws_cloudwatch_exporter.py
```

## Grafana Dashboard

The exporter includes a pre-configured Grafana dashboard (`grafana/dashboards/aws.json`) with:

- **Overview Panel**: Total running instances gauge
- **Distribution Charts**: Instance types and availability zones
- **CPU Utilization Table**: Real-time CPU usage per instance
- **Volume Size Table**: EBS volume sizes and types
- **Network Traffic Graphs**: Network in/out over time

### Import Dashboard
1. Open Grafana UI
2. Go to Dashboards → Import
3. Upload the `aws.json` file
4. Configure the Prometheus datasource

## Metrics Reference

### Prometheus Metrics

| Metric Name | Type | Labels | Description |
|-------------|------|--------|-------------|
| `aws_ec2_running_instances_total` | Gauge | - | Total number of running instances |
| `aws_ec2_cpu_utilization_percent` | Gauge | instance_id, instance_type, availability_zone, name | CPU utilization percentage |
| `aws_ec2_memory_utilization_percent` | Gauge | instance_id, instance_type, availability_zone, name | Memory utilization percentage |
| `aws_ec2_network_in_bytes` | Gauge | instance_id, instance_type, availability_zone, name | Network bytes in |
| `aws_ec2_network_out_bytes` | Gauge | instance_id, instance_type, availability_zone, name | Network bytes out |
| `aws_ec2_instance_type_count` | Gauge | instance_type | Count of instances by type |
| `aws_ec2_availability_zone_count` | Gauge | availability_zone | Count of instances by AZ |
| `aws_ebs_volume_size_gb` | Gauge | volume_id, instance_id, instance_name, volume_type | Volume size in GB |
| `aws_ebs_volume_queue_length` | Gauge | volume_id, instance_id, instance_name, volume_type | Volume queue length |
| `aws_ebs_volume_read_ops_total` | Gauge | volume_id, instance_id, instance_name, volume_type | Volume read operations |
| `aws_ebs_volume_write_ops_total` | Gauge | volume_id, instance_id, instance_name, volume_type | Volume write operations |
| `aws_ebs_volume_utilization_percent` | Gauge | volume_id, instance_id, instance_name, volume_type, device | Volume utilization percentage |
| `aws_ebs_volume_free_space_gb` | Gauge | volume_id, instance_id, instance_name, volume_type, device | Volume free space in GB |
| `aws_ebs_volume_used_space_gb` | Gauge | volume_id, instance_id, instance_name, volume_type, device | Volume used space in GB |

## Troubleshooting

### Common Issues

1. **No Credentials Error**:
   ```
   Error: AWS credentials not found
   ```
   - Solution: Configure AWS credentials as described above

2. **Permission Denied**:
   ```
   AWS API Error: Access Denied
   ```
   - Solution: Ensure your AWS user/role has the required permissions

3. **No Data in Grafana**:
   - Check if the exporter is running without errors
   - Verify Push Gateway is receiving metrics
   - Ensure Grafana can connect to Prometheus

4. **Missing Memory Metrics**:
   - Install and configure CloudWatch agent on EC2 instances
   - Memory metrics are optional and require additional setup

### Debug Mode
Run with verbose output:
```bash
python -m sw360_dashboard.aws_cloudwatch_exporter
```

### Check Push Gateway
Verify metrics are being pushed:
```bash
curl http://localhost:9091/metrics | grep aws_
```

## Cost Considerations

- CloudWatch API calls have costs associated
- The exporter uses efficient API calls but monitor your AWS bill
- Consider adjusting the collection frequency based on your needs
- EBS and EC2 metrics are included in the free tier up to certain limits

## Security Best Practices

1. Use IAM roles instead of access keys when possible
2. Apply least privilege principle to AWS permissions
3. Rotate access keys regularly if using them
4. Monitor AWS CloudTrail for API access logs
5. Use VPC endpoints for CloudWatch API calls if running in VPC
