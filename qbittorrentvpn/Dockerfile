# qBittorrent with OpenVPN/WireGuard - ARM64 Compatible
# Based on DyonR/docker-qbittorrentvpn with ARM64 modifications
# Modified for Raspberry Pi 5 (aarch64)

FROM debian:bookworm-slim

WORKDIR /opt

# Pin versions for reproducible builds
# Note: qBittorrent 5.x requires Qt6, but Debian bookworm only has Qt5
# Using qBittorrent 4.6.7 (last Qt5-compatible version)
ARG LIBTORRENT_VERSION=2.0.10
ARG QBITTORRENT_VERSION=4.6.7

RUN usermod -u 99 nobody

# Make directories
RUN mkdir -p /downloads /config/qBittorrent /etc/openvpn /etc/qbittorrent

# Install all dependencies
RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends \
        # Build dependencies
        build-essential \
        ca-certificates \
        cmake \
        curl \
        git \
        libboost-dev \
        libboost-system-dev \
        libboost-chrono-dev \
        libboost-random-dev \
        libssl-dev \
        ninja-build \
        pkg-config \
        qtbase5-dev \
        qttools5-dev \
        zlib1g-dev \
        # Runtime dependencies
        dos2unix \
        inetutils-ping \
        ipcalc \
        iptables \
        kmod \
        libqt5network5 \
        libqt5xml5 \
        libqt5sql5 \
        libssl3 \
        moreutils \
        net-tools \
        openresolv \
        openvpn \
        openssl \
        procps \
        wireguard-tools \
        p7zip-full \
        unzip \
        zip

# Build libtorrent-rasterbar
RUN echo "Building libtorrent-rasterbar ${LIBTORRENT_VERSION}..." \
    && curl -sL "https://github.com/arvidn/libtorrent/releases/download/v${LIBTORRENT_VERSION}/libtorrent-rasterbar-${LIBTORRENT_VERSION}.tar.gz" -o /opt/libtorrent.tar.gz \
    && tar -xzf /opt/libtorrent.tar.gz \
    && rm /opt/libtorrent.tar.gz \
    && cd /opt/libtorrent-rasterbar-${LIBTORRENT_VERSION} \
    && cmake -G Ninja -B build \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX:PATH=/usr \
        -DCMAKE_CXX_STANDARD=17 \
    && cmake --build build --parallel $(nproc) \
    && cmake --install build \
    && cd /opt \
    && rm -rf /opt/libtorrent-rasterbar-${LIBTORRENT_VERSION}

# Build qBittorrent
RUN echo "Building qBittorrent ${QBITTORRENT_VERSION}..." \
    && curl -sL "https://github.com/qbittorrent/qBittorrent/archive/release-${QBITTORRENT_VERSION}.tar.gz" -o /opt/qbittorrent.tar.gz \
    && tar -xzf /opt/qbittorrent.tar.gz \
    && rm /opt/qbittorrent.tar.gz \
    && cd /opt/qBittorrent-release-${QBITTORRENT_VERSION} \
    && cmake -G Ninja -B build \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX=/usr/local \
        -DGUI=OFF \
        -DCMAKE_CXX_STANDARD=17 \
    && cmake --build build --parallel $(nproc) \
    && cmake --install build \
    && cd /opt \
    && rm -rf /opt/qBittorrent-release-${QBITTORRENT_VERSION}

# Cleanup build dependencies
RUN apt-get purge -y \
        build-essential \
        cmake \
        git \
        libboost-dev \
        libboost-system-dev \
        libboost-chrono-dev \
        libboost-random-dev \
        libssl-dev \
        ninja-build \
        pkg-config \
        qtbase5-dev \
        qttools5-dev \
        zlib1g-dev \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Remove src_valid_mark from wg-quick (causes issues in containers)
RUN sed -i /net\.ipv4\.conf\.all\.src_valid_mark/d $(which wg-quick)

VOLUME /config /downloads

# Copy scripts
COPY openvpn/ /etc/openvpn/
COPY qbittorrent/ /etc/qbittorrent/

RUN chmod +x /etc/qbittorrent/*.sh /etc/qbittorrent/*.init /etc/openvpn/*.sh

EXPOSE 8080
EXPOSE 8999
EXPOSE 8999/udp

CMD ["/bin/bash", "/etc/openvpn/start.sh"]
