# Docker Usage

You can run Financial Tracker using Docker for easy deployment and environment consistency.

## 1. Build the Docker Image

From the project root directory, run:

```sh
docker build -t financial-tracker .
```

## 2. Run the Docker Container

Make sure you have a `.env` file in your project root with all required environment variables.

Run the following command:

```sh
docker run --env-file .env -p 5000:5000 financial-tracker
```

- The app will be available at [http://localhost:5000](http://localhost:5000)
- The `--env-file .env` flag loads your environment variables into the container.
- The `-p 5000:5000` flag maps the container's port 5000 to your host.

## 3. Stopping the Container

Press `Ctrl+C` in the terminal running Docker, or stop the container using Docker Desktop or:

```sh
docker ps  # Find your container ID
docker stop <container_id>
```