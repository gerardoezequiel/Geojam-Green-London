variable "cloudflare_api_token"  { type = string, sensitive = true }
variable "cloudflare_account_id" { type = string }
variable "cloudflare_zone_id"    { type = string }
variable "vercel_api_token"      { type = string, sensitive = true }
variable "vercel_team_slug"      { type = string, default = "gerardoezequiel" }
variable "vercel_team_id"        { type = string, default = "team_vDeAFAr6tfJEEcvfxUavreth" }
variable "github_token"          { type = string, sensitive = true }
variable "github_owner"          { type = string, default = "gerardoezequiel" }
