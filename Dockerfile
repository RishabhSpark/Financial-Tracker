# Use official Python image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy client_secret.json explicitly (ensure it is not in .dockerignore)
COPY client_secret.json ./

# Copy project files
COPY . .

# Expose the port Flask runs on
EXPOSE 5000

# Set environment variables for Flask
ENV FLASK_APP=app:app
ENV FLASK_RUN_HOST=0.0.0.0
ENV FLASK_ENV=development

# Run the application
CMD ["python", "app.py"]
