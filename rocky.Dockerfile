FROM rockylinux:9 AS base

RUN dnf install -y \
    'dnf-command(config-manager)' \
    python3.12

ENV GZ_PARTITION=multicosim

FROM base AS build

RUN dnf group install -y "Development Tools"
RUN dnf config-manager --enable devel crb 
RUN dnf install -y \
    epel-release \
    epel-next-release \
    cmake

