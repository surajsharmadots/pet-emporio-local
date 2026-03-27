FROM python:3.12-slim

WORKDIR /app

# Install pe-common from monorepo
COPY packages/pe-common /app/packages/pe-common
RUN pip install --no-cache-dir /app/packages/pe-common

# Install service dependencies
COPY services/user-service/requirements.txt /app/service/requirements.txt
WORKDIR /app/service
RUN pip install --no-cache-dir -r requirements.txt

# Copy service source
COPY services/user-service /app/service

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]