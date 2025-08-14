FROM ghcr.io/cpslab-asu/multicosim/rocky/base:9.6 AS base

RUN dnf group install -y "Development Tools"
RUN dnf config-manager --enable devel crb 
RUN dnf install -y \
    epel-release \
    epel-next-release \
    cmake

