# Use a slim Python 3.11 image for a small footprint
FROM python:3.11-slim

# Set environment variables for Python
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Create an unprivileged user for security
RUN groupadd -r etims && useradd -r -g etims etims

# Set the working directory
WORKDIR /app

# Install system dependencies if required
RUN apt-get update && apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Ensure data directory exists and is owned by the unprivileged user
RUN mkdir -p data && chown -R etims:etims /app

# Switch to the unprivileged user
USER etims

# Expose the application port
EXPOSE 8000

# Run the application with Gunicorn, listening on the PORT env variable (required by Railway/Render)
CMD sh -c "gunicorn --bind 0.0.0.0:${PORT:-8000} --workers 4 app:app"
