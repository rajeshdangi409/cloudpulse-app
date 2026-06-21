# CloudPulse — Application (CI/CD)

> **App repo** — a Flask web app that is built, tested, containerized, and deployed to AWS EKS through a fully automated Jenkins pipeline.

This repository holds the application code and the Jenkins pipeline that ships it.
The Kubernetes manifests live in a **separate `cloudpulse-config` repo** (see below).
It is the last code piece of a **5-repo** project.

---

## The 5 Repositories

```
Phase 1 → cloudpulse-bootstrap   → Creates Jenkins + Ansible EC2   [Terraform, run locally]
Phase 2 → cloudpulse-ansible     → Configures the Jenkins server    [Ansible, from Ansible server]
Phase 3 → cloudpulse-infra       → Creates VPC + EKS + ECR          [Terraform via Jenkins]
Phase 4 → cloudpulse-app         → Builds, tests, pushes to ECR     [Jenkins, on every push] (THIS)
            └─ commits new image tag to ▼
          cloudpulse-config       → K8s manifests; Flux deploys it  [GitOps target — no webhook]
```

> **Why a separate config repo?** The app pipeline commits the new image tag to
> `cloudpulse-config`, which has **no Jenkins webhook**. If that commit went back
> into `cloudpulse-app` it would re-trigger the build — an infinite loop. Splitting
> the manifests out breaks that loop cleanly.

---

## What Happens When I Push Code?

```
git push (app code) → Webhook → Jenkins → Lint & Test → Docker Build → ECR Push
                                                                            │
                       commit new image tag to cloudpulse-config repo ◄────┘
                                                  │
                                                  ▼
                                  FluxCD (inside the cluster) sees the
                                  config-repo commit → deploys to EKS ✅
```

Every push to `main` auto-triggers the pipeline via a GitHub webhook. This is a
**GitOps / pull-based** flow: Jenkins never runs `kubectl apply` — it only
commits the new image tag to the **separate `cloudpulse-config` repo**, and
**Flux** (running inside the cluster) detects the change and deploys it. Because
the tag commit lands in `cloudpulse-config` (which has no webhook), it never
re-triggers this build — so there is **no CI loop**.

---

## Tools Used

| Tool | Purpose |
|------|---------|
| Python Flask | Simple web application |
| pytest + flake8 | Unit tests + linting (runs in the pipeline) |
| Docker | Containerize the app |
| GitHub | Source code + webhook trigger |
| Jenkins | CI/CD pipeline automation |
| Kubernetes (EKS) | Run & scale app containers |
| AWS ECR | Private Docker image registry |
| FluxCD | GitOps controller — deploys from Git into the cluster |

---

## Repository Structure

```
cloudpulse-app/
├── app/
│   ├── main.py                 # Flask app (/ and /health)
│   ├── test_main.py            # pytest unit tests
│   ├── requirements.txt        # Runtime deps (flask, gunicorn)
│   ├── requirements-dev.txt    # CI-only deps (pytest, flake8)
│   ├── Dockerfile
│   ├── .dockerignore           # Excludes tests/dev files from the image
│   └── templates/
│       └── index.html
├── jenkins/
│   ├── Jenkinsfile             # Lint & Test → Build → Push ECR → Commit tag to config repo
│   └── Jenkinsfile.cleanup     # Separate job — Flux uninstall + delete namespace + ECR images
├── .gitignore
└── README.md
```

> The Kubernetes manifests (`namespace.yaml`, `deployment.yaml`, `service.yaml`,
> `kustomization.yaml`) now live in the **`cloudpulse-config`** repo — that is the
> repo Flux watches and deploys from.

---

## The Pipeline (`jenkins/Jenkinsfile`)

| Stage | What it does |
|-------|--------------|
| Checkout | Pulls the repo |
| Lint & Test | `flake8` + `pytest` (build stops if a test fails) |
| Build Docker Image | `docker build` tagged with the build number |
| Push to ECR | Authenticates and pushes the image to ECR |
| Update Image Tag (Config Repo) | Clones `cloudpulse-config`, bumps the tag in its `k8s/deployment.yaml`, and **git push** — Flux deploys it |
| Email | Success/failure notification |

All repeated values (region, account, cluster, namespace, app name, email) live
in a single `environment {}` block at the top — no values are hardcoded inside
the stages.

> **GitOps:** the pipeline does **not** run `kubectl apply`. It only commits the
> new image tag to the **`cloudpulse-config`** repo; Flux (inside the cluster)
> does the actual deploy. The git push uses a Jenkins **`github-token`**
> credential (Secret text, `repo` scope).

> A separate **cleanup** job (`jenkins/Jenkinsfile.cleanup`) uninstalls Flux
> (so it can't self-heal the app back), then deletes the K8s resources and ECR
> images on demand, behind a confirmation gate.

---

## The Application

```python
# app/main.py
@app.route("/")        # returns the version page
@app.route("/health")  # returns {"status": "ok"} — used by K8s probes
```

The version shown in the browser comes from `main.py` (currently `4.0`).
To release a new version: edit the version in `main.py` → `git push` → the
pipeline rebuilds, pushes to ECR, and commits the new tag to the `cloudpulse-config`
repo → Flux deploys it → the browser shows the new version.

### Tests
```bash
cd app
pip install -r requirements.txt -r requirements-dev.txt
pytest -v        # 5 tests covering / and /health
```

---

## Kubernetes Labels

All manifests (in the **`cloudpulse-config`** repo) use the **recommended**
`app.kubernetes.io/*` labels so each resource's role is explicit:

```yaml
app.kubernetes.io/name: cloudpulse-app
app.kubernetes.io/instance: cloudpulse-app
app.kubernetes.io/component: backend
app.kubernetes.io/part-of: cloudpulse
app.kubernetes.io/managed-by: flux
```

> The Service selector intentionally uses only `name` + `instance` (selectors are
> immutable, so no version/changing labels are included there).

---

## GitHub Webhook Setup

1. GitHub repo → Settings → Webhooks → Add webhook
2. **Payload URL:** `http://<jenkins-ip>:8080/github-webhook/`
3. **Content type:** `application/json`
4. **Events:** Just the push event
5. Jenkins job → Build Triggers → ✅ `GitHub hook trigger for GITScm polling`

---

## Quick Reference Commands

```bash
# Check running pods
kubectl get pods -n cloudpulse

# Check app URL (LoadBalancer)
kubectl get svc -n cloudpulse

# Run the app pipeline manually
# Jenkins → cloudpulse-app → Build Now

# Tear down app resources (separate job)
# Jenkins → cloudpulse-app-cleanup → Build → confirm
# (uninstalls Flux, then deletes K8s resources + ECR images)
```

> ⚠️ **EKS is not free!** Destroy the infrastructure after the demo via the
> `cloudpulse-infra` **destroy pipeline**. See `docs/RUNBOOK.md` for full steps.

---

## GitOps with FluxCD

This project uses **FluxCD** for deployments — a **pull-based / GitOps** model:

```
Jenkins builds + pushes to ECR → commits new tag to cloudpulse-config
                                         │
                                         ▼
              Flux (inside EKS) watches the cloudpulse-config repo's
              k8s/ folder every ~1 min → applies any change automatically
```

**Why GitOps?**
- **Git is the single source of truth** — the cluster always matches Git.
- **Self-healing** — if someone changes the cluster manually, Flux reverts it
  back to the Git-declared state.
- Jenkins no longer needs cluster-admin access — it only pushes to ECR and
  commits to Git.
- **No CI loop** — the manifests live in a config repo with no webhook, so the
  image-tag commit never re-triggers the app build.

**How Flux gets there:** the `cloudpulse-infra` create pipeline runs
`flux bootstrap` once after the EKS cluster is created. That command installs
Flux into the cluster and auto-commits the `GitRepository` + `Kustomization`
manifests into the **`cloudpulse-config`** repo under `k8s/flux-system/`.

> The full design rationale (push vs pull, alternatives considered) is documented
> in [`docs/FLUXCD_PLAN.md`](../docs/FLUXCD_PLAN.md).

