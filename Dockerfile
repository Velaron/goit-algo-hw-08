FROM python:3.13.5-slim

WORKDIR /app

COPY . .

CMD ["python", "main.py"]