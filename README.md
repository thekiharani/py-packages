# `noria-py`

Python package monorepo for Noria Labs.

Published packages:

- `noriacomm`: messaging SDK for SMS and WhatsApp provider integrations
- `norialog`: structured JSON logging for Python services
- `noriapay`: payments SDK for M-PESA Daraja, SasaPay, and Paystack
- `noriastore`: S3 and R2 storage client for Python services

Quick install examples:

```bash
pip install noriacomm
pip install norialog
pip install noriapay
pip install noriastore
```

Repo layout:

- `noriacomm/`
- `norialog/`
- `noriapay/`
- `noriastore/`

Each package is versioned and published from its own directory, with package-specific docs in its local `README.md`.
