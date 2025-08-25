# Use the official Ubuntu image as the base
FROM ubuntu:20.04

# Set the environment variable for non-interactive installations
ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV PYENV_SHELL=/bin/bash
ENV PYTHONUNBUFFERED=1

# Install required dependencies
RUN apt-get update && \
    apt-get install -y curl apt-transport-https ca-certificates gnupg lsb-release openssh-client unzip

# Install AWS CLI v2 (architecture-aware)
RUN ARCH=$(dpkg --print-architecture) && \
    if [ "$ARCH" = "arm64" ] || [ "$ARCH" = "aarch64" ]; then \
        curl "https://awscli.amazonaws.com/awscli-exe-linux-aarch64.zip" -o "awscliv2.zip"; \
    else \
        curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"; \
    fi && \
    unzip awscliv2.zip && \
    ./aws/install && \
    rm -rf awscliv2.zip aws/

# Docker
RUN install -m 0755 -d /etc/apt/keyrings
RUN curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
RUN chmod a+r /etc/apt/keyrings/docker.gpg
RUN echo "deb [arch="$(dpkg --print-architecture)" signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
    "$(. /etc/os-release && echo "$VERSION_CODENAME")" stable" | \
    tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install packages
RUN apt-get update && \
    apt-get install -y jq docker-ce

# Python
RUN apt-get update && \
    apt-get install -y --no-install-recommends python3.9 python3-pip && \
    pip install pipenv

RUN useradd -ms /bin/bash app -d /home/app -u 1000 -p "$(openssl passwd -1 passw0rd)" && \
    usermod -aG docker app && \
    mkdir -p /app && \
    chown app:app /app

# Switch to the new user
USER app
WORKDIR /app

# Install python packages
ADD --chown=app:app Pipfile /app/

# Generate Pipfile.lock with correct dependencies and install
RUN cd /app && pipenv lock && pipenv sync

# Add the rest of the source code. This is done last so we don't invalidate all
# layers when we change a line of code.
ADD --chown=app:app . /app

# Entry point
ENTRYPOINT ["/bin/bash","./docker-entrypoint.sh"]