# ---- Builder Stage ----
# Use a full Python image to build dependencies, which can be cached
FROM python:3.13 as builder

WORKDIR /opt/venv

# Create a virtual environment to isolate dependencies
RUN python -m venv .
ENV PATH="/opt/venv/bin:$PATH"

# Copy only the requirements file to leverage Docker cache
COPY ./requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# ---- Final Stage ----
# Use a slim image for a smaller final footprint
FROM python:3.13-slim

WORKDIR /app

# Copy the virtual environment from the builder stage
COPY --from=builder /opt/venv /opt/venv

# Copy the application source code
COPY . /app/

# Set the PATH to use the virtual environment
ENV PATH="/opt/venv/bin:$PATH"

# Run as a non-root user for better security
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser

# Expose the port and run the application
EXPOSE 8000
CMD ["fastapi", "run", "main.py", "--host", "0.0.0.0", "--port", "8000"]
