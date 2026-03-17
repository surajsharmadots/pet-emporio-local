FROM python:3.12-slim

WORKDIR /app

# Install pe-common from monorepo
COPY packages/pe-common /app/packages/pe-common
RUN pip install --no-cache-dir /app/packages/pe-common

# Install service dependencies
COPY services/auth-service/pyproject.toml /app/service/
WORKDIR /app/service
RUN pip install --no-cache-dir -e .

# Copy service source
COPY services/auth-service /app/service

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]