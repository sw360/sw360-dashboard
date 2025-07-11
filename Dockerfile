# SPDX-License-Identifier: EPL-2.0
# Copyright Siemens AG, 2025. Part of the SW360 Portal Project.
#
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# Run the Dashboard scripts to fetch data for Grafana in docker-compose

FROM python:3.13-alpine

ARG DASHBOARD_VERSION
ARG GROUPS

RUN pip install sw360-dashboard==$DASHBOARD_VERSION \
 && printf '0 20 * * * sw360-exporter $GROUPS\n' > /etc/crontabs/root \
 && chmod 0644 /etc/crontabs/root

CMD [ "crond", "-f" ]
