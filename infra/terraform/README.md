# Green Cities — Terraform

Infrastructure-as-code for the Green Cities project. One `terraform apply` provisions Cloudflare R2 + DNS, Vercel project + Blob + Edge Config, and pushes secrets into GitHub Actions.

## Layout

```
infra/terraform/
  main.tf                  # composition
  variables.tf
  outputs.tf
  modules/
    cloudflare_r2/         # bucket + CORS + lifecycle
    cloudflare_dns/        # CNAMEs for tiles. and app.
    vercel_project/        # Next.js project + env vars + git integration
    vercel_blob_store/     # OG images, user uploads
    vercel_edge_config/    # city manifest registry
    github_actions_secrets/# CI credentials
```

## State

Remote state in **Terraform Cloud** (free tier), workspace `green-cities-prod`, organisation `gerardoezequiel`.

```sh
terraform init
terraform plan
terraform apply
```

## CI

`.github/workflows/terraform.yml`:

- `pull_request`: `terraform fmt -check`, `tflint`, `tfsec`, `terraform plan`
- `push` to `main`: `terraform apply -auto-approve`

## Required env vars (set in Terraform Cloud)

- `TF_VAR_cloudflare_api_token`
- `TF_VAR_cloudflare_account_id`
- `TF_VAR_cloudflare_zone_id`
- `TF_VAR_vercel_api_token`
- `TF_VAR_github_token`

## OpenTofu

`terraform` and `tofu` binaries are interchangeable for this project. Swap if HashiCorp licensing matters.
