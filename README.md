<!--
 SPDX-License-Identifier: MIT
 SPDX-FileCopyrightText: 2025 Siemens AG
-->
# Dashboard

Script to gather information for SW360 dashboard.

## Installation

1. Setup and install [poetry](https://python-poetry.org/docs/#installation).
2. Install the packages with `poetry install`.
3. Generate the group specific files with the following command:
    - Group specific files are generated to create specific metrics for
      `businessUnit`, a.k.a. Tags of a project.
    - This helps you generate detailed metrics for each business unit using
      your SW360 instance.
    - Let's say you have business units like `DEPT`, `DEPT2`, etc., you can
      generate files for each of them in following manner (case-sensitive):
        ```sh
        poetry run generate-groups DEPT DEPT2
        ```
    - You **must** run this command for at least one business unit.
    - This will create files under `src/sw360_dashboard` package and Grafana
      dashboards under `grafana/dashboards/` directory.
4. Create `.env` from `.env.example`, set the actual values and set
   `DRY_RUN=false` to push actual data.
5. To run, `sw360-exporter <groups>` where `<groups>` is a space-separated list
   of business units you want to generate metrics for. Default is all groups.
6. Optionally, setup a cron job run by non-root user (e.g. `sw360`):
    1. Setup a non-root user (e.g. `sw360`) (optional, but recommended):
       ```sh
       sudo adduser sw360
       ```
    2. Create log directory:
       ```sh
       sudo mkdir -p /var/log/sw360/
       sudo chown -R sw360:sw360 /var/log/sw360/
       ```
    3. Copy the helper script [dashboard_cron.sh](dashboard_cron.sh) to a
       location accessible by `sw360` user.
    4. As `sw360 user`, edit cron tab with `crontab -e` and add the
       following line:
       ```sh
       0 20 * * * cd /path/to/dashboard_cron.sh && /path/to/dashboard_cron.sh >> /var/log/sw360/dashboard.log 2>&1
       ```
       This will run the script every day at 20:00.

## Files

### Utility Scripts

`couchdb_utils.py` contains utility functions for interacting with CouchDB,
creating views, fetching results, and pushing metrics to Prometheus.

### Exporter Scripts

`couchdb_DEPT_exporter.py` scripts are responsible for fetching data from
CouchDB for different project tags and pushing metrics to Prometheus.

`couchdb_CLI_exporter.py` script generates the metrics of CLX attachments used
per business unit.

`couchdb_common_metrics.py` script generates the common metrics like type of
components, number of projects over time, etc.

### CLI Script

`cli.py` provides a command-line interface to run the exporter scripts for
specified business units.

### Dashboard Scripts

- `dashboard_cron.sh` is a helper script to run the exporter scripts as a cron
  job.
- `grafana` directory contains the Grafana dashboards and configuration files
  for Grafana itself and the Apache reverse proxy configuration.

## Setup the dashboard

**Note:** the scripts here assume you are using the non-root using `sw360` as
described in _Installation > 5. > 1._

### 1. Install Prometheus

1. Download latest and stable version of Prometheus from the
   [official website](https://prometheus.io/download/) and extract it to
   `/opt/prometheus/`.
2. Change the ownership of the directory:
   ```sh
   sudo chown -R sw360:sw360 /opt/prometheus/
   ```
3. Create a systemd service file at `/etc/systemd/system/prometheus.service`
   for Prometheus:
   ```ini
   [Unit]
   Description=Prometheus server
   Wants=network-online.target
   After=network-online.target

   [Service]
   User=sw360
   Group=sw360
   Type=simple
   Restart=always
   WorkingDirectory=/opt/prometheus
   RuntimeDirectory=prometheus
   RuntimeDirectoryMode=0750
   ExecStart=/opt/prometheus/prometheus \
       --config.file=/opt/prometheus/prometheus.yml \
       --storage.tsdb.retention.time=7d

   LimitNOFILE=10000
   TimeoutStopSec=20

   [Install]
   WantedBy=multi-user.target
   ```
4. Enable and start the Prometheus service:
   ```sh
   sudo systemctl daemon-reload
   sudo systemctl enable prometheus
   sudo systemctl start prometheus
   ```

### 2. Install Prometheus Pushgateway

1. Download latest and stable version of Prometheus Pushgateway from the
   [official website](https://prometheus.io/download/) and extract it to
   `/opt/pushgateway/`.
2. Change the ownership of the directory:
   ```sh
   sudo chown -R sw360:sw360 /opt/pushgateway/
   ```
3. Create a systemd service file at `/etc/systemd/system/pushgateway.service`
   for Prometheus Pushgateway:
   ```ini
   [Unit]
   Description=Prometheus Pushgateway server
   Wants=network-online.target
   After=prometheus.target

   [Service]
   User=sw360
   Group=sw360
   Type=simple
   Restart=always
   WorkingDirectory=/opt/pushgateway/
   RuntimeDirectory=pushgateway
   RuntimeDirectoryMode=0750
   ExecStart=/opt/pushgateway/pushgateway
   
   LimitNOFILE=10000
   TimeoutStopSec=20

   [Install]
   WantedBy=multi-user.target
   ```
4. Enable and start the Prometheus Pushgateway service:
   ```sh
   sudo systemctl daemon-reload
   sudo systemctl enable pushgateway
   sudo systemctl start pushgateway
   ```
5. Make sure Prometheus is scraping the Pushgateway. Add the following to
   `/opt/prometheus/prometheus.yml`:
   ```yaml
   scrape_configs:
     - job_name: 'pushgateway'
       static_configs:
         - targets: ['localhost:9091']
   ```

### 3. Install Grafana

1. Install Grafana (check the
   [official installation guide](https://grafana.com/docs/grafana/latest/setup-grafana/installation/debian/#install-from-apt-repository)):
   ```sh
   sudo apt-get install -y grafana
   ```
2. Modify the Grafana config at `/etc/grafana/grafana.ini` with values from
   [grafana/grafana.ini](grafana/grafana.ini)
3. Enable and start the Grafana service:
   ```sh
   sudo systemctl enable grafana-server
   sudo systemctl start grafana-server
   ```

**Note:** After setting the `auth.proxy` in grafana.ini, you need to login with
your user first, disable the `auth.proxy` and login with the admin user. Then
promote your user as an admin user. After that, you can enable the
`auth.proxy` again.

### 4. Import Grafana dashboards

Once above steps are completed, you can import the dashboards into Grafana. Make
sure you've run the `poetry run generate-groups DEPT DEPT2` from
[installation step 3](#installation) otherwise the `grafana/dashboards/`
directory will be empty.

1. Open Grafana and navigate to the "Dashboards" section.
2. Setup the datasource:
    - Click on "Add data source".
    - Select "Prometheus" and configure it to point to your Prometheus server.
    - For example, by default it will be running on `http://localhost:9090`.
    - Click "Save & Test" to verify the connection.
3. Click on "Manage" and then "Import".
4. Upload the JSON files from the [grafana/dashboards/](grafana/dashboards)
   directory.

#### 4. a. Alternatively, use Grafana providers

Grafana also allows automated setup with
[Grafana provisioning](https://grafana.com/docs/grafana/latest/administration/provisioning/)
and this repo contains helper scripts for the same under
[grafana/provisioning](grafana/provisioning).
Find your provisioning directory and data directory from your
[grafana config](https://grafana.com/docs/grafana/latest/setup-grafana/configure-grafana/#path),
which defaults to `/etc/grafana/provisioning` and `/var/lib/grafana`
respectively. If the locations are not default, you would have to update the
[grafana/provisioning/datasources.yaml](grafana/provisioning/datasources.yaml)
and fix the path to data directory.
Once done, copy following files to their respective location (update the path
according to your setup) for provisioning.

1. Shutdown the Grafana if running.
2. Provision the datasource:
   `sudo cp grafana/provisioning/datasources.yaml /etc/grafana/provisioning/datasources/prometheus.yaml`
3. Copy the dashboards: `sudo cp -r grafana/dashboards /var/lib/grafana/dashboards/`
4. Provision the dashboards:
   `sudo cp grafana/provisioning/dashboards.yaml /etc/grafana/provisioning/dashboards/darshboard.yaml`

Once done, at the next start of Grafana, it should autoconfigure the
datasource and dashboards for you.

### 5. Configure Apache Reverse proxy with mellon

If you are using Apache as your reverse proxy and Mellon for SAML based
authentication, you can refer to the
[grafana/apache-sw360.conf](grafana/apache-sw360.conf) file as
reference and update the Apache2 enabled site serving the SW360 application.
