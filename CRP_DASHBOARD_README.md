<!--
 SPDX-License-Identifier: MIT
 SPDX-FileCopyrightText: 2025 Innomotics
-->
# SW360 Components, Releases & Projects Dashboard

## Overview

This dashboard provides comprehensive visualization of the relationships between components, releases, and projects in the SW360 system. It displays metrics collected from the `collect_components_releases_projects_data.py` script and exported via the `couchdb_CRP_exporter.py` Prometheus exporter.

## Performance Optimization

The dashboard tables are optimized to show only the **top 50 results** for better performance and readability:

- **Top 50 Components by Release Count**: Shows components with the most releases first
- **Top 50 Releases by Project Usage**: Shows releases used by the most projects first  
- **Top 50 Components Without Releases**: Shows first 50 components that lack releases

This limitation ensures fast loading times while still providing the most relevant insights for decision-making.

## Features

### Overview Metrics
- **Total Components**: Total number of components in the system
- **Total Releases**: Total number of releases in the system  
- **Total Projects**: Total number of projects in the system
- **Unused Components**: Number of components without any releases

### Components Analysis
- **Components by Type**: Pie chart showing distribution of components by type (OSS, COTS, Internal, etc.)
- **Relationship Summary**: Statistics about components with releases, releases with projects, and orphaned releases (displayed side-by-side with Components by Type)

### Time Series Analysis
- **Creation Trends Over Time**: Line chart showing components and releases created per year

### Detailed Component-Release Relationships
- **Top 50 Components by Release Count**: Table showing components with the highest number of releases
- **Top 50 Releases by Project Usage**: Table showing releases with the highest number of projects using them

### Components Without Releases
- **Top 50 Components Without Releases**: Details table of components lacking releases (limited to first 50 results)

## Data Collection Script

The dashboard is powered by data from `collect_components_releases_projects_data.py` which:

1. **Collects all components** from the SW360 database
2. **Collects all releases** and maps them to their parent components
3. **Collects all projects** and identifies which releases they use
4. **Analyzes relationships** between components, releases, and projects
5. **Generates comprehensive reports** in JSON and CSV formats

### Key Data Points
- Components with their metadata (name, type, creation date)
- Releases linked to each component with version information
- Projects using each release with usage counts
- Orphaned releases (releases without valid component references)

## Prometheus Exporter

The `couchdb_CRP_exporter.py` script converts the collected data into Prometheus metrics. The exporter has been optimized to only generate metrics that are actively used by the dashboard, ensuring efficient resource usage.

### Metrics Exported

#### Overview Metrics
- `crp_total_components` - Total number of components
- `crp_total_releases` - Total number of releases  
- `crp_total_projects` - Total number of projects
- `crp_components_with_releases` - Components that have releases
- `crp_components_without_releases` - Components without releases
- `crp_releases_with_projects` - Releases linked to projects
- `crp_releases_without_projects` - Releases not linked to projects
- `crp_orphaned_releases` - Orphaned releases (missing component)

#### Detailed Metrics
- `crp_components_by_type{component_type}` - Components grouped by type
- `crp_component_release_count{component_id, component_name, component_type}` - Release count per component
- `crp_release_project_count{release_id, release_name, release_version, component_name}` - Project count per release

#### Time-based Metrics
- `crp_components_created_per_year{year}` - Components created per year
- `crp_releases_created_per_year{year}` - Releases created per year

## Running the Data Collection

### 1. Run the Collection Script
```bash
cd /home/sw360/dashboard
python3 -m src.sw360_dashboard.collect_components_releases_projects_data
```

This generates:
- JSON report with complete data structure
- CSV summary for spreadsheet analysis

### 2. Run the Prometheus Exporter
```bash
cd /home/sw360/dashboard  
python3 -m src.sw360_dashboard.couchdb_CRP_exporter
```

This exports metrics to Prometheus Push Gateway for Grafana visualization.

### 3. View Dashboard
- Access Grafana at your configured URL
- Navigate to the "SW360 Components, Releases & Projects Dashboard"
- Metrics will be automatically refreshed based on your exporter schedule

## Configuration

### Database Connection
The scripts use the same CouchDB configuration as other SW360 dashboard components:
- Host: `localhost:5984` (configurable via environment variables)
- Database: `sw360db`
- Authentication: Admin credentials

### Prometheus Push Gateway
Metrics are pushed to the configured Push Gateway:
- URL: `localhost:9091` (configurable via `PUSHGATEWAY_URL` environment variable)
- Job name: `crp_exporter`

## Scheduling

Consider adding the exporter to a cron job for regular updates:

```bash
# Run every hour
0 * * * * cd /home/sw360/dashboard && python3 -m src.sw360_dashboard.couchdb_CRP_exporter
```

## Troubleshooting

### Common Issues

1. **No data in dashboard**: Ensure the exporter has run successfully and pushed metrics
2. **CouchDB connection errors**: Verify database connectivity and credentials
3. **Missing components**: Check if the component type filters in queries match your data

### Debug Commands

Check if metrics are being pushed:
```bash
curl http://localhost:9091/metrics | grep crp_
```

Verify CouchDB connectivity:
```bash
curl http://localhost:5984/sw360db/_design/_view/by_type?key="component"&limit=1
```

### Log Analysis

The exporter provides detailed console output showing:
- Number of components, releases, and projects processed
- Summary statistics
- Push gateway success confirmation

## Performance Optimization

The dashboard tables are optimized to show only the **top 50 results** for better performance and readability:

- **Top 50 Components by Release Count**: Shows components with the most releases first
- **Top 50 Releases by Project Usage**: Shows releases used by the most projects first  
- **Top 50 Components Without Releases**: Shows first 50 components that lack releases

This limitation ensures fast loading times while still providing the most relevant insights for decision-making.

The dashboard JSON can be modified to:
- Add new panels for additional metrics
- Adjust time ranges and refresh intervals  
- Customize visualizations and color schemes
- Add filters for specific component types or date ranges

## Related Components

This dashboard complements other SW360 dashboards:
- **Global Dashboard**: Overall SW360 system metrics
- **Component Dashboard**: Detailed component analysis
- **Project Dashboard**: Project-specific metrics
