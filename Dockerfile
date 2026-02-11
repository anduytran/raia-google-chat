# Smaller, light-weight version of Python
FROM python:3.9-slim

# Makes the working directory /app for organization
WORKDIR /app

# Install dependencies, using --no-cache-dir to reduce image size
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy everything else
COPY . .

# Google Cloud Run expects port 8080
ENV PORT=8080
EXPOSE 8080

# Start the server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]