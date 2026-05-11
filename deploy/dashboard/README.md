# Proof-of-Action Dashboard

This is the canonical hosted dashboard for Proof-of-Action. It is the deploy
target for the public boundary surface and the only dashboard built in PR CI.

Required local validation:

```bash
npm ci
npm run lint
npm run build
```

The repository root `dashboard/` directory is a legacy/local prototype kept for
reference. Changes intended for the hosted product should land here under
`deploy/dashboard/`.
