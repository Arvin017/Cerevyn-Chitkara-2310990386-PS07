# Azure deployment plan

> Status: **design only**. Nothing in this repository has been deployed to Azure; live deployment is optional in the
> assessment. The application runs locally and in Docker (see `README.md`). The steps below are the intended
> procedure and use placeholders; check commands against your current Azure CLI version before running them.

## 1. Workload

The tool turns two dated red/NIR images plus a farm mask into NDVI statistics, a heatmap and downloadable results.
Per-scene work is small (NumPy over at most 1 M pixels in this build), bursty and stateless, which favours low-cost,
small hosting. Real satellite tiles (e.g. Sentinel-2 at ~10 000 x 10 000 px) would need windowed reads clipped to the
farm polygon (see section 7); that is not implemented here.

## 2. Architecture

```
 Analyst browser --HTTPS--> Azure App Service (Linux container)  --> Application Insights
                              FastAPI app + dashboard                   (requests, errors, latency)
                                 |  managed identity (no keys)
                                 v
                         Azure Blob Storage
                         |- container "scenes"   (uploaded .npz / source rasters)
                         '- container "results"  (<run_id>/results.json, pixels.csv, heatmap.png)

 GitHub Actions --OIDC--> Azure Container Registry --> App Service pulls the image
```

| Concern | Choice | Why |
|---|---|---|
| Compute | App Service for Containers, Linux, plan B1 (dev/test) | Runs the same Dockerfile as local; simple and predictable cost. Container Apps (consumption, scale to zero) is the alternative for very sparse traffic. |
| Storage | Blob Storage (StorageV2, LRS) | Replaces the local `output/` folder. Run folders are named by the deterministic `run_id`, so identical inputs rewrite identical files (idempotent). |
| Images | Azure Container Registry (Basic) | Holds the image built by CI. |
| Batch option | Azure Functions, Blob trigger on `scenes` | Process dropped files without an interactive session. The analysis code is already separate from the web layer (`core.py`, `io.py`, `report.py`). |
| Monitoring | Application Insights + Log Analytics | Request latency and failures, with `run_id` as a custom dimension for traceability. |

## 3. Identity and secret handling

* The app needs **no secrets**. A system-assigned managed identity on the Web App gets `Storage Blob Data Contributor`
  on the storage account only (least privilege) and `AcrPull` on the registry. No account keys or SAS tokens in code
  or config; the app would use `DefaultAzureCredential`.
* GitHub Actions authenticates with **OIDC federated credentials** (`azure/login`), not a stored client secret.
  Repository variables `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` identify the app registration;
  they are identifiers, not credentials.
* Settings come from the names in `.env.example`. Anything that later becomes sensitive goes into Key Vault and is
  referenced from App Service with a Key Vault reference.
* Uploads are untrusted: `.npz` is loaded with `allow_pickle=False`, uploads are capped at 5 MB and 1 M pixels, and
  download routes accept only 12-hex-character run ids (no path traversal).

## 4. Deployment steps (intended)

1. Create a resource group, a storage account with `scenes` and `results` containers, a container registry, Log Analytics
   plus Application Insights, and a Linux App Service plan.
2. Create the Web App from the container image and enable its system-assigned identity.
3. Assign `Storage Blob Data Contributor` (storage account scope) and `AcrPull` (registry scope) to that identity.
4. Create an Entra app registration with a federated credential bound to this GitHub repository; grant it `Contributor`
   on the resource group only.
5. Add a manually triggered `deploy.yml` (`workflow_dispatch`): `azure/login` (OIDC), build and push the image to ACR,
   then point the Web App at the new tag. `ci.yml` (tests plus container health check) already exists and must pass first.
6. Set app settings and the health-check path `/health`, then verify that `POST /api/analyze/sample` returns `decline_flagged`.

## 5. Monitoring

* Application Insights: request rate, failure rate, p95 latency; alerts on failed-request rate and HTTP 5xx.
* One structured log line per run with `run_id`, input shape and decision status (no pixel data, no personal data).
* App Service health check on `/health`.

## 6. Cost-control assumptions

* One B1 instance (or Container Apps consumption scaling to zero); no autoscale in dev/test.
* Blob lifecycle rules: `results` to Cool after 30 days and delete after 180 days; `scenes` deleted after 90 days.
* LRS redundancy, Basic ACR, an Application Insights daily cap, and an Azure budget alert at a fixed monthly limit.
* Delete the resource group after the assessment; everything is reproducible from this repository.

## 7. Scaling (not implemented)

Read cloud-optimised GeoTIFF windows clipped to the farm polygon instead of whole tiles, derive the validity mask from the
product's own cloud / scene-classification layer, and run batches through the Functions blob trigger with a queue for retries.
