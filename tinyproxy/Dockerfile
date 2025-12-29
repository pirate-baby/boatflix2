FROM alpine:latest

RUN apk add --no-cache tinyproxy

EXPOSE 8118

CMD ["tinyproxy", "-d", "-c", "/etc/tinyproxy/tinyproxy.conf"]
