# Base image: slim keeps size down vs full python image
FROM python:3.12-slim

# Set working directory inside the container
WORKDIR /app

# Copy ONLY requirements first — this layer caches separately
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Now copy the rest of the app code
COPY . .

# Document which port the app uses
EXPOSE 5000

# The command that runs when the container starts
CMD ["python", "app.py"]