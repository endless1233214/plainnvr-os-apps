FROM python:3.14-alpine3.24

RUN apk add --no-cache ffmpeg \
    && addgroup -S -g 568 plainnvr \
    && adduser -S -D -H -u 568 -G plainnvr plainnvr

WORKDIR /app
COPY motion.py /app/motion.py
USER 568:568
ENTRYPOINT ["python", "/app/motion.py"]
