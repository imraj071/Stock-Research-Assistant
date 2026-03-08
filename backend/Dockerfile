FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Set LangSmith env vars at container level so they're available before imports
ENV LANGCHAIN_TRACING_V2=true

EXPOSE 8000