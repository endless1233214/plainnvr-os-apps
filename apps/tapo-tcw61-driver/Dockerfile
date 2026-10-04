# The helper is built from a pinned PlainNVR commit so the sidecar and core
# share exactly the same TPAP/SPAKE2+ implementation.
ARG PLAINNVR_REF=47b38798d7a0993d1803a76761c7715ba22750be
FROM golang:1.27.1-alpine3.24 AS helper-build
ARG PLAINNVR_REF
RUN apk add --no-cache ca-certificates git
RUN git clone https://github.com/endless1233214/plainnvr.git /src \
    && git -C /src checkout --detach "$PLAINNVR_REF"
WORKDIR /src/build/tapoctl
RUN go test ./... \
    && CGO_ENABLED=0 go build -mod=readonly -trimpath -o /plainnvr-tapoctl .

FROM python:3.14-alpine3.24
RUN addgroup -S -g 568 plainnvr && adduser -S -D -H -u 568 -G plainnvr plainnvr
COPY --from=helper-build /plainnvr-tapoctl /usr/local/bin/plainnvr-tapoctl
COPY driver.py /app/driver.py
RUN chmod 0555 /usr/local/bin/plainnvr-tapoctl /app/driver.py
USER 568:568
ENV DRIVER_BIND=0.0.0.0 \
    DRIVER_PORT=8789 \
    DRIVER_HELPER_TIMEOUT=15
EXPOSE 8789
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8789/health', timeout=3).read()"
ENTRYPOINT ["python", "/app/driver.py"]
