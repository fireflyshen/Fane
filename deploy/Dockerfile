FROM python:3.12-slim

WORKDIR /bills
COPY fane-2.1.0-py3-none-any.whl constraints.txt /tmp/
RUN pip install --no-cache-dir -c /tmp/constraints.txt /tmp/fane-2.1.0-py3-none-any.whl \
    && rm /tmp/fane-2.1.0-py3-none-any.whl /tmp/constraints.txt

ENV FANE_MODULES=query
EXPOSE 8080
ENTRYPOINT ["fa"]
CMD ["serve", "--ledger", "/bills/main.bean", "--host", "0.0.0.0", "--port", "8080"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request; assert urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=4).status == 200"
