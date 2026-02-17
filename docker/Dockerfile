FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .
RUN pip install --no-cache-dir -e .

EXPOSE 8000

CMD ["tui", "gateway", "--host", "0.0.0.0", "--port", "8000"]
