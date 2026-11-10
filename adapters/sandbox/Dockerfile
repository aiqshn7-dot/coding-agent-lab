FROM python:3.12-slim

RUN pip install --no-cache-dir pytest \
    && useradd --create-home --uid 1000 --shell /usr/sbin/nologin runner

USER runner
WORKDIR /workspace

CMD ["pytest", "-q", "-p", "no:cacheprovider"]
