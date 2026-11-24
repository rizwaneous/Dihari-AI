FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv
RUN pip install fastapi "uvicorn[standard]" "sqlalchemy>=2" pydantic pydantic-settings httpx fastmcp psycopg2-binary python-multipart tzdata pywebpush
COPY backend backend
COPY config config
COPY locales locales
WORKDIR /srv/backend
EXPOSE 8000
CMD ["sh", "scripts/start.sh"]
