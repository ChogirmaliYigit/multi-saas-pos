# TLS 1.2+ only. 1.0 and 1.1 are deprecated and fail a PCI scan, which matters
# for anything sitting next to card payments.
ssl_protocols TLSv1.2 TLSv1.3;
ssl_prefer_server_ciphers off;
ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305;

ssl_session_timeout 1d;
ssl_session_cache shared:SSL:10m;
ssl_session_tickets off;

# OCSP stapling: the browser gets the revocation proof from us instead of
# making its own round trip to the CA.
ssl_stapling on;
ssl_stapling_verify on;
resolver 127.0.0.11 valid=30s;
resolver_timeout 5s;
