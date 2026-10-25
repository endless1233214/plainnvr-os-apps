FROM python:3.14-alpine3.24

RUN addgroup -S -g 568 plainnvr && adduser -S -D -H -u 568 -G plainnvr plainnvr
WORKDIR /app
COPY driver.py /app/driver.py
USER 568:568
ENV VICTURE_DRIVER_BIND=0.0.0.0 VICTURE_DRIVER_PORT=8795 \
    VICTURE_DRIVER_TOKEN_FILE=/run/secrets/victure_driver_token \
    PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
EXPOSE 8795
ENTRYPOINT ["python", "/app/driver.py"]
