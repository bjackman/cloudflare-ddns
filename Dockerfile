# ---- Base ----
FROM timothyjmiller/cloudflare-ddns AS dependencies

#
# ---- Release ----
FROM dependencies AS release
# copy project source file(s)
WORKDIR /
COPY cloudflare-ddns.py .
CMD ["python", "-u", "/cloudflare-ddns.py", "--repeat"]
