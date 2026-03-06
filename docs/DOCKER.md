# Docker Compose Layout

The `docker/` directory uses a **multi-file Docker Compose** setup so new services can be added without touching existing configs.

## Structure

```
docker/
├── .env.example   ← copy to .env and fill in secrets (gitignored)
├── core.yml       ← defines the shared "homelab" Docker network
└── immich.yml     ← Immich stack (postgres, redis, server, ML)
```

Future stacks (Nextcloud, Jellyfin, Ollama) each get their own file and attach to the same `homelab` network — no changes needed to `immich.yml`.

## First-Time Setup

```bash
cd /opt/homelab          # or wherever you deploy this repo
cp docker/.env.example docker/.env
nano docker/.env         # fill in passwords, storage paths, GPU IDs

docker compose --env-file docker/.env \
  -f docker/core.yml -f docker/immich.yml up -d
```

## Everyday Commands

```bash
# Start / restart Immich
docker compose --env-file docker/.env \
  -f docker/core.yml -f docker/immich.yml up -d

# Stop Immich (other stacks keep running)
docker compose --env-file docker/.env \
  -f docker/core.yml -f docker/immich.yml down

# Follow logs
docker compose --env-file docker/.env \
  -f docker/core.yml -f docker/immich.yml logs -f

# Pull image updates (then re-run `up -d` to apply)
docker compose --env-file docker/.env \
  -f docker/core.yml -f docker/immich.yml pull
```

## GPU Assignment

Each GPU-using service has its own variable in `docker/.env`. To change which GPU a service uses — including after a hardware swap — edit only the `.env` file:

```bash
# List GPU indices and UUIDs on your host:
nvidia-smi --query-gpu=index,name,uuid --format=csv

# Then in docker/.env:
IMMICH_ML_GPU_ID=0    # index, or a full UUID like GPU-abc123...
JELLYFIN_GPU_ID=1     # different GPU, no changes to any compose file

# Apply:
docker compose --env-file docker/.env \
  -f docker/core.yml -f docker/immich.yml up -d immich-ml
```

**CPU-only mode:** Remove or comment out the `deploy:` block in `docker/immich.yml` under the `immich-ml` service.

## Switching to a mergerfs Storage Pool

Update the bind mount in `docker/.env` — no compose file edits needed:

```bash
# docker/.env
IMMICH_UPLOAD_LOCATION=/mnt/storage/immich/library
```

Keep the database (`immich_db_data` named volume) on your OS/SSD drive. Random I/O on spinning disks in a mergerfs pool degrades PostgreSQL performance.

## Adding Future Services

Each new service gets its own compose file. The pattern is always the same:

**1. Create the compose file** (example: `docker/jellyfin.yml`)

```yaml
services:
  jellyfin:
    image: jellyfin/jellyfin:latest
    container_name: jellyfin
    restart: unless-stopped
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              device_ids: ["${JELLYFIN_GPU_ID:-0}"]
              capabilities: [gpu]
    volumes:
      - ${JELLYFIN_CONFIG_DIR}:/config
      - ${JELLYFIN_MEDIA_DIR}:/media:ro
    expose:
      - "8096"      # no host binding — Caddy routes here by container name
    networks:
      - homelab

networks:
  homelab:
    external: true
    name: homelab
```

**2. Add variables to `docker/.env`**

```bash
JELLYFIN_GPU_ID=0
JELLYFIN_CONFIG_DIR=./data/jellyfin/config
JELLYFIN_MEDIA_DIR=/mnt/storage/media
```

**3. Start the new stack** (Immich keeps running untouched)

```bash
docker compose --env-file docker/.env \
  -f docker/core.yml -f docker/jellyfin.yml up -d
```

Follow the same pattern for Nextcloud (`nextcloud.yml`) and Ollama (`ollama.yml`).

## Adding a Reverse Proxy (Caddy)

Create `docker/proxy.yml`. Because all services join the `homelab` network, Caddy reaches them by container name without any host port bindings:

```yaml
# docker/proxy.yml
services:
  caddy:
    image: caddy:2-alpine
    container_name: caddy
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
      - "443:443/udp"   # HTTP/3
    volumes:
      - ./caddy/Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    networks:
      - homelab

volumes:
  caddy_data:
    name: caddy_data
  caddy_config:
    name: caddy_config

networks:
  homelab:
    external: true
    name: homelab
```

```
# docker/caddy/Caddyfile
photos.yourdomain.com {
    reverse_proxy immich-server:2283
}
cloud.yourdomain.com {
    reverse_proxy nextcloud:80
}
media.yourdomain.com {
    reverse_proxy jellyfin:8096
}
ai.yourdomain.com {
    reverse_proxy ollama:11434
}
```

Once Caddy is running, change the `127.0.0.1:2283:2283` port binding in `docker/immich.yml` to `expose: ["2283"]` so Immich is only reachable through the proxy.
