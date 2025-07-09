# Docker Usage

You can run Financial Tracker using Docker for easy deployment and environment consistency.
## 1. Build using Docker Compose

Build and start all services in the background:

```sh
docker compose up -d --build
```

- The `--build` flag ensures any code changes are included.
- The `-d` flag runs containers in detached mode.

To stop all running containers:

```sh
docker compose down
```

To view logs for all services:

```sh
docker compose logs -f
```

## 5. Rebuilding After Code Changes

Whenever you make changes to the code or dependencies, rebuild and restart the containers:

```sh
docker compose up -d --build
```

This ensures your changes are reflected in the running containers.