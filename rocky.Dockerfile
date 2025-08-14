FROM rockylinux:9 AS base

RUN dnf install -y \
    'dnf-command(config-manager)' \
    python3.12

ENV GZ_PARTITION=multicosim
