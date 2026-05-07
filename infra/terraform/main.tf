terraform {
  required_version = ">= 1.7.0"

  cloud {
    organization = "gerardoezequiel"
    workspaces { name = "green-cities-prod" }
  }

  required_providers {
    cloudflare = { source = "cloudflare/cloudflare", version = "~> 4.40" }
    vercel     = { source = "vercel/vercel",         version = "~> 1.10" }
    github     = { source = "integrations/github",   version = "~> 6.2"  }
  }
}

provider "cloudflare" {
  api_token = var.cloudflare_api_token
}

provider "vercel" {
  api_token = var.vercel_api_token
  team      = var.vercel_team_slug
}

provider "github" {
  token = var.github_token
  owner = var.github_owner
}

module "r2" {
  source                  = "./modules/cloudflare_r2"
  account_id              = var.cloudflare_account_id
  bucket_name             = "green-cities"
  cors_allowed_origins    = ["https://green.cities", "https://*.vercel.app", "http://localhost:3000"]
  cors_allowed_headers    = ["Range", "Content-Type"]
  cors_max_age_seconds    = 86400
}

module "vercel_project" {
  source        = "./modules/vercel_project"
  name          = "green-london"
  framework     = "nextjs"
  git_repository = {
    type = "github"
    repo = "${var.github_owner}/Geojam-Green-London"
  }
  environment_variables = {
    R2_ACCESS_KEY_ID         = { value = module.r2.access_key_id,     target = ["production","preview"], type = "encrypted" }
    R2_SECRET_ACCESS_KEY     = { value = module.r2.secret_access_key, target = ["production","preview"], type = "encrypted" }
    R2_S3_ENDPOINT           = { value = module.r2.s3_endpoint,       target = ["production","preview","development"], type = "plain" }
    NEXT_PUBLIC_R2_BUCKET_URL= { value = module.r2.public_url,        target = ["production","preview","development"], type = "plain" }
    NEXT_PUBLIC_VERCEL_EDGE_CONFIG = { value = module.edge_config.connection_string, target = ["production","preview","development"], type = "encrypted" }
  }
}

module "blob" {
  source     = "./modules/vercel_blob_store"
  store_name = "green-cities-blob"
  region     = "fra1"
  access     = "public"
}

module "edge_config" {
  source         = "./modules/vercel_edge_config"
  store_name     = "green-cities-registry"
  initial_items  = {
    cities = file("../../cities/_index.json")
  }
}

module "github_secrets" {
  source     = "./modules/github_actions_secrets"
  repository = "Geojam-Green-London"
  secrets = {
    R2_ACCESS_KEY_ID     = module.r2.access_key_id
    R2_SECRET_ACCESS_KEY = module.r2.secret_access_key
    R2_S3_ENDPOINT       = module.r2.s3_endpoint
    VERCEL_TOKEN         = var.vercel_api_token
    VERCEL_ORG_ID        = var.vercel_team_id
    VERCEL_PROJECT_ID    = module.vercel_project.id
  }
}

module "dns" {
  source       = "./modules/cloudflare_dns"
  zone_id      = var.cloudflare_zone_id
  records = {
    "tiles.green.cities" = { type = "CNAME", value = module.r2.public_hostname, proxied = true }
    "app.green.cities"   = { type = "CNAME", value = "cname.vercel-dns.com",     proxied = false }
  }
}
