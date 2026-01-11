<!--
 SPDX-License-Identifier: EPL-2.0
 SPDX-FileCopyrightText: 2025 Siemens AG
-->
# SW360 Dashboard Ansible Automation

This Ansible playbook automates the installation and configuration of the SW360 Dashboard infrastructure components as described in the main README.md.

## Overview

The playbook automates the following three main steps from the README:

1. **Install Prometheus** - Downloads, installs, and configures Prometheus with systemd service
2. **Install Prometheus Pushgateway** - Downloads, installs, and configures Pushgateway with systemd service  
3. **Install Grafana** - Installs Grafana from the official repository and configures it

## Prerequisites

### System Requirements
- Ubuntu/Debian-based system
- Root/sudo access
- Internet connectivity for downloading packages

### Install Ansible
```bash
# On Ubuntu/Debian
sudo apt update
sudo apt install ansible

# On CentOS/RHEL
sudo yum install ansible
# or
sudo dnf install ansible

# Verify installation
ansible --version
```

## Directory Structure

```
ansible/
├── playbook.yml           # Main Ansible playbook
├── templates/             # Jinja2 templates (if any)
└── README.md             # This file
```

## Configuration

### Variables

The playbook uses the following variables (defined in `vars` section):

```yaml
# Software versions
prometheus_version: "2.47.2"
pushgateway_version: "1.6.2"

# Installation paths
install_dir: "/opt"
user: "username"        # Replace with your actual username
group: "groupname"      # Replace with your actual group name
```

**Important:** You must update the `user` and `group` variables in the playbook before running it.

### Customization

You can customize the installation by modifying the variables in the playbook:

```yaml
vars:
  prometheus_version: "2.47.2"      # Change Prometheus version
  pushgateway_version: "1.6.2"      # Change Pushgateway version
  install_dir: "/opt"                # Change installation directory
  user: "username"                   # Change service user (REQUIRED)
  group: "groupname"                 # Change service group (REQUIRED)
```

**Note:** The `user` and `group` variables are placeholders and must be updated with actual values before running the playbook.

## Usage

### Prerequisites Configuration

**Before running the playbook, you MUST:**

1. **Update the inventory file** (`inventory`) with your actual server details
2. **Update the playbook variables** - Replace `username` and `groupname` with actual values:
   ```yaml
   user: "your_actual_username"
   group: "your_actual_groupname"
   ```
3. **Update the hosts target** - Replace `foss360` with your actual inventory group name

### Basic Usage

1. **Navigate to the ansible directory:**
   ```bash
   cd /path/to/dashboard/ansible
   ```

2. **Run the playbook:**
   ```bash
   ansible-playbook playbook.yml
   ```

3. **Run with verbose output:**
   ```bash
   ansible-playbook playbook.yml -v
   ```

#### Run with different inventory
```bash
ansible-playbook -i inventory.yml playbook.yml
```

## What the Playbook Does

### Step 1: Install Prometheus
- Downloads Prometheus v2.47.2 from GitHub releases
- Extracts and installs to `/opt/prometheus/`
- Creates systemd service file with specified user/group
- Enables and starts Prometheus service
- Configures retention time to 7 days

### Step 2: Install Prometheus Pushgateway
- Downloads Pushgateway v1.6.2 from GitHub releases
- Extracts and installs to `/opt/pushgateway/`
- Creates systemd service file with specified user/group
- Enables and starts Pushgateway service
- Configures Prometheus to scrape Pushgateway metrics

### Step 3: Install Grafana
- Adds official Grafana APT repository
- Installs Grafana package
- Configures Grafana to use port 3001
- Enables and starts Grafana service

### Additional Tasks
- Installs Poetry for Python dependency management
- Creates necessary directories with proper permissions
- Configures systemd services with proper user/group ownership
- Provides detailed completion summary with next steps

## Service Information

After successful execution, the following services will be running:

| Service | Port | URL | Description |
|---------|------|-----|-------------|
| Prometheus | 9090 | http://localhost:9090 | Metrics collection and storage |
| Pushgateway | 9091 | http://localhost:9091 | Metrics pushing gateway |
| Grafana | 3001 | http://localhost:3001 | Dashboard and visualization |

## Post-Installation Steps

1. **Configure Grafana Datasource:**
   - Open http://localhost:3001
   - Login with admin/admin
   - Add Prometheus datasource: http://localhost:9090

2. **Import Dashboards:**
   - Navigate to Dashboards → Import
   - Upload JSON files from `grafana/dashboards/` directory

3. **Install SW360 Dashboard Package:**
   - Clone this repository to your desired location
   - Navigate to the repository: `cd /path/to/sw360-dashboard`
   - Install dependencies: `poetry install`
   - Generate group files: `poetry run generate-groups <business_units>`
   - Configure environment: `cp .env.example .env` and edit with your SW360 credentials

4. **Setup Cron Job:**
   - Configure automated data collection
   - Setup log rotation

## Troubleshooting

### Service Management

```bash
# Check service status
sudo systemctl status prometheus
sudo systemctl status pushgateway
sudo systemctl status grafana-server

# Start/stop services
sudo systemctl start prometheus
sudo systemctl stop prometheus
sudo systemctl restart prometheus

# Enable/disable services
sudo systemctl enable prometheus
sudo systemctl disable prometheus

# View logs
sudo journalctl -u prometheus -f
sudo journalctl -u pushgateway -f
sudo journalctl -u grafana-server -f
```

### Configuration Files

| Component | Configuration File | Service File |
|-----------|-------------------|--------------|
| Prometheus | `/opt/prometheus/prometheus.yml` | `/etc/systemd/system/prometheus.service` |
| Pushgateway | N/A | `/etc/systemd/system/pushgateway.service` |
| Grafana | `/etc/grafana/grafana.ini` | `/etc/systemd/system/grafana-server.service` |

## Verification

### Health Checks
```bash
# Check if services are responding
curl http://localhost:9090/-/healthy
curl http://localhost:9091/-/healthy
curl http://localhost:3001/api/health

# Check Prometheus targets
curl http://localhost:9090/api/v1/targets

# Check Pushgateway metrics
curl http://localhost:9091/metrics
```

### Log Files
```bash
# View service logs
sudo journalctl -u prometheus --since "1 hour ago"
sudo journalctl -u pushgateway --since "1 hour ago"
sudo journalctl -u grafana-server --since "1 hour ago"
```
