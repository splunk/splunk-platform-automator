# Fixture for the docs+skills secret scan (not operator docs)

A PEM body must not appear in docs or skills:

-----BEGIN PRIVATE KEY-----
MIIB
-----END PRIVATE KEY-----

Agent skills must not pass `-v` on deploy:

```bash
spa deploy --yes -v
```
