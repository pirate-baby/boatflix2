# qBittorrent with OpenVPN/WireGuard - ARM64 Compatible
# Based on DyonR/docker-qbittorrentvpn with ARM64 modifications
# Modified for Raspberry Pi 5 (aarch64)

FROM debian:bookworm-slim

WORKDIR /opt

# Set architecture - will be overridden by buildx
ARG TARGETARCH=arm64

RUN usermod -u 99 nobody

# Make directories
RUN mkdir -p /downloads /config/qBittorrent /etc/openvpn /etc/qbittorrent

# Install build dependencies and boost
# Using Debian packages for ARM64 compatibility instead of downloading x86 binaries
RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        cmake \
        curl \
        git \
        jq \
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
    && rm -rf /var/lib/apt/lists/*

# Compile and install libtorrent-rasterbar (required for qBittorrent)
RUN LIBTORRENT_ASSETS=$(curl -sX GET "https://api.github.com/repos/arvidn/libtorrent/releases" | jq '.[] | select(.prerelease==false) | select(.target_commitish=="RC_2_0") | .assets_url' | head -n 1 | tr -d '"') \
    && LIBTORRENT_DOWNLOAD_URL=$(curl -sX GET ${LIBTORRENT_ASSETS} | jq '.[0] .browser_download_url' | tr -d '"') \
    && LIBTORRENT_NAME=$(curl -sX GET ${LIBTORRENT_ASSETS} | jq '.[0] .name' | tr -d '"') \
    && curl -o /opt/${LIBTORRENT_NAME} -L ${LIBTORRENT_DOWNLOAD_URL} \
    && tar -xzf /opt/${LIBTORRENT_NAME} \
    && rm /opt/${LIBTORRENT_NAME} \
    && cd /opt/libtorrent-rasterbar* \
    && cmake -G Ninja -B build \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX:PATH=/usr \
        -DCMAKE_CXX_STANDARD=17 \
    && cmake --build build --parallel $(nproc) \
    && cmake --install build \
    && cd /opt \
    && rm -rf /opt/*

# Compile and install qBittorrent
RUN QBITTORRENT_RELEASE=$(curl -sX GET "https://api.github.com/repos/qBittorrent/qBittorrent/tags" | jq '.[] | select(.name | index ("alpha") | not) | select(.name | index ("beta") | not) | select(.name | index ("rc") | not) | .name' | head -n 1 | tr -d '"') \
    && echo "Building qBittorrent version: ${QBITTORRENT_RELEASE}" \
    && curl -o /opt/qBittorrent-${QBITTORRENT_RELEASE}.tar.gz -L "https://github.com/qbittorrent/qBittorrent/archive/${QBITTORRENT_RELEASE}.tar.gz" \
    && tar -xzf /opt/qBittorrent-${QBITTORRENT_RELEASE}.tar.gz \
    && rm /opt/qBittorrent-${QBITTORRENT_RELEASE}.tar.gz \
    && cd /opt/qBittorrent-${QBITTORRENT_RELEASE} \
    && cmake -G Ninja -B build \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX=/usr/local \
        -DGUI=OFF \
        -DCMAKE_CXX_STANDARD=17 \
    && cmake --build build --parallel $(nproc) \
    && cmake --install build \
    && cd /opt \
    && rm -rf /opt/*

# Clean up build dependencies and install runtime dependencies
RUN apt-get purge -y \
        build-essential \
        cmake \
        git \
        jq \
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
    && rm -rf /var/lib/apt/lists/*

# Install runtime dependencies, VPN tools, and utilities
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
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
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install compression tools
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        p7zip-full \
        unzip \
        zip \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

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
