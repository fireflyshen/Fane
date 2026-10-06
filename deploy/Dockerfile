FROM python:3.12-slim

WORKDIR /bills
COPY pyproject.toml README.md LICENSE /src/
COPY fane /src/fane
RUN pip install --no-cache-dir /src && rm -rf /src

EXPOSE 8080
ENTRYPOINT ["fa"]
CMD ["serve", "--ledger", "/bills/main.bean", "--host", "0.0.0.0", "--port", "8080"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request; assert urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=4).status == 200"
