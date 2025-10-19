FROM python:3.10-slim

RUN pip install fastapi uvicorn faster-whisper python-multipart

COPY server.py /app/server.py

WORKDIR /app

EXPOSE 8000

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]