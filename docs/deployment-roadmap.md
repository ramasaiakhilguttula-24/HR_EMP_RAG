# Deployment Roadmap (F19 + F20) — beginner path

Goal: a live URL where anyone can register, upload HR docs, and get cited answers —
with every `git push` tested before it ships. Two tracks: **A = live fast** (Railway),
**B = learn DevOps deeply** (AWS + Terraform). Do A first, B after.

Vocabulary (used below):
- **Image**: a frozen snapshot of an app (code + dependencies). Built from a Dockerfile.
- **Container**: a running instance of an image.
- **Registry**: a store for images (like GitHub for code). AWS ECR / Railway internal.
- **CI**: automation that checks every push (tests, eval gate). **CD**: automation that ships it.
- **IaC (Terraform)**: cloud servers described as code files instead of console clicks.

---

## Track A — Railway (hours, ~$5–20/mo, free trial credit)

### A0. Prerequisites (you)
1. GitHub account. Push this repo (`.gitignore` already protects `.env`).
2. Railway account (railway.app) — sign up with GitHub, free trial credit included.
3. Our F19 prep (me): multi-stage Dockerfiles, frontend API-URL build-arg, healthchecks.

### A1. Put the code on GitHub (you + me)
```bash
git init && git add -A && git commit -m "HR RAG v1" && git push
```
Why: every deploy and CI run starts from git. (I will walk you through it.)

### A2. Create the project (you, clicks)
Railway → New Project → Deploy from GitHub repo. Then **add services**:
- Postgres plugin (managed database — no Docker needed for it)
- Redis plugin (managed cache/queue)
- Qdrant: New Service → Docker image `qdrant/qdrant:v1.19.1` + persistent volume on `/qdrant/storage`
- Backend: our repo, root `backend/` Dockerfile
- Frontend: our repo, root `frontend/` Dockerfile

### A3. Wire environment variables (you, copy-paste)
Backend service → Variables: paste everything from `.env`, with hostnames swapped to
Railway's internal names (e.g. `DATABASE_URL` → the Postgres plugin's URL variable).
Frontend service → Variables: `NEXT_PUBLIC_API_URL=<backend-public-url>`.
Secrets live in Railway, never in git. This replaces `.env` in production.

### A4. First boot: database + knowledge (me + you)
1. Run one-off command on backend service: `python scripts/init_db.py` (creates tables).
2. Upload `sample_docs/` via the Admin UI (or leave empty and upload your own).
3. Open `/health` and `/ready` on the backend URL — both must say up/ready.

### A5. CI/CD (me, you watch and learn)
- GitHub Actions (already scaffolded in `.github/workflows/`): on every push →
  install → `pytest` → eval gate (runs when API secrets are set as repo secrets).
- Railway auto-deploys the `main` branch on every green push. That IS the CD step.
- You will deliberately break a test once, watch the pipeline stop the deploy, then fix it.
  That lesson is the whole point of F20.

### A6. Go live (you)
- Railway → Settings → Generate Domain → you get `https://<app>.up.railway.app`.
- Share it. Monitor via Admin → Insights + LangSmith traces (same as local).

**What you learn in Track A:** git-based deploys, env vars vs secrets, managed services,
logs, domains, CI gates. No cloud networking knowledge required.

---

## Track B — AWS + Terraform (days, real DevOps — after A is live)

### B0. Prerequisites (you)
1. AWS account + billing alarm FIRST (Billing → Budgets → $10 alert; this is step zero).
2. AWS CLI + Terraform installed locally. I guide each install.

### B1. Identity & state (learn: least privilege)
- IAM user for GitHub Actions with only ECR/ECS rights (no root keys, ever).
- S3 bucket for Terraform state (so infra config is shared, not on one laptop).

### B2. Network (learn: VPC)
- Terraform: VPC + public/private subnets + security groups (only ALB faces the internet).

### B3. Data layer (learn: managed services)
- RDS Postgres (Multi-AZ) + ElastiCache Redis via Terraform. Qdrant stays a container
  (AWS has no managed Qdrant) on ECS with an EFS/EBS volume.

### B4. Secrets (learn: no secrets in code/env files)
- API keys → AWS Secrets Manager; ECS injects them at runtime.

### B5. App hosting (learn: orchestration)
- Push images to ECR → ECS services (backend/frontend/worker) behind an ALB that uses
  our `/health` + `/ready` endpoints → auto-scaling on CPU → CloudFront in front of frontend.

### B6. Full pipeline (learn: promotion gates)
- GitHub Actions: test → eval gate → build images → deploy staging → manual approval →
  production. Same shape as Track A, AWS as the target.

---

## Order of work (agreed sequence)
1. F19-prep (me): Dockerfiles, build-args, healthchecks, DB-init story.
2. Track A live (you + me, this week).
3. F17 eval resume (me, background) — gates protect both tracks.
4. Track B (you + me, when you want the deep end).

## Costs & warnings
- Railway: trial credit first; hobby usage roughly a coffee per month. Set spend limits.
- AWS: create the **billing alarm before anything else**; idle RDS/ALB cost money even
  with zero traffic. Destroy (`terraform destroy`) what you are not using.
