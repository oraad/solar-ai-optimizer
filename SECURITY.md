# Security Policy

## Supported Versions

| Version | Supported |
| ------- | --------- |
| 0.1.x   | Yes       |

## Reporting a Vulnerability

Please report security issues privately:

1. Open a [GitHub Security Advisory](https://github.com/oraad/solar-ai-optimizer/security/advisories/new), or
2. Email **omarraad@gmail.com** with a description and reproduction steps.

Do not open public issues for undisclosed vulnerabilities.

## Deployment Guidance

- When exposing the API outside Home Assistant ingress, set `API_TOKEN` and use HTTPS.
- Keep Home Assistant long-lived tokens scoped and rotated.
- Run in **shadow mode** until you trust automated inverter writes.
- The default Docker image includes optional ML/MPC extras; use `INSTALL_EXTRAS=0` for a leaner attack surface if those features are unused.
