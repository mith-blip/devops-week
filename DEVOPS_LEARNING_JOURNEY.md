# DevOps Learning Journey — Days 1 to 4

A hands-on, free-of-cost DevOps learning log built around a single running project: a Python Flask app that is containerized, tested through a CI/CD pipeline, and published to artifact registries. Each day pairs the **concept** with the **hands-on work** and the **interview questions** that topic generates.

**Stack used (all free):** Docker, Docker Compose, Python/Flask, GitHub Actions, GitHub Container Registry (GHCR), Sonatype Nexus OSS.

---

## Table of Contents

- [Day 1 — Docker & Containerizing a Python App](#day-1--docker--containerizing-a-python-app)
- [Day 2 — Docker Compose (App + Postgres + Redis)](#day-2--docker-compose-app--postgres--redis)
- [Day 3 — CI/CD with GitHub Actions](#day-3--cicd-with-github-actions)
- [Day 4 — Artifact Management: Registries & Nexus OSS](#day-4--artifact-management-registries--nexus-oss)
- [Day 5 — Kubernetes Core: Pods, Deployments, Services](#day-5--kubernetes-core-pods-deployments-services)
- [Cross-cutting lessons learned](#cross-cutting-lessons-learned-the-debugging-that-taught-the-most)

---

## Day 1 — Docker & Containerizing a Python App

### Concepts

A **container** is a process running in isolation on the host, using Linux kernel features: **namespaces** (isolate what a process can *see* — filesystem, network, other processes) and **cgroups** (isolate what it can *use* — CPU, memory). It is **not** a VM: a VM virtualizes hardware and runs a full guest OS with its own kernel, while a container shares the host kernel and isolates only userspace. That is why containers start in milliseconds.

Core terms:

- **Image** — a read-only template (app + dependencies + filesystem snapshot), built in layers.
- **Container** — a running or stopped instance of an image, with a writable layer on top.
- **Dockerfile** — the recipe that builds an image.
- **Registry** — where images are stored and shared.
- **Layer** — each Dockerfile instruction creates a cached filesystem layer; ordering affects build speed.

### The app

`app.py` (Flask service with a `/health` endpoint for later Kubernetes checks). Key detail: it listens on `host="0.0.0.0"`, not `127.0.0.1`, so it is reachable from outside the container.

`requirements.txt` pins versions (`flask==3.0.3`) for reproducible builds.

### The Dockerfile

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 5000
CMD ["python", "app.py"]
```

**Most important concept:** `requirements.txt` is copied and installed *before* the rest of the code. Docker caches each layer, so the expensive `pip install` layer is reused unless dependencies change — only the cheap code layer rebuilds. Order a Dockerfile from least-frequently-changing to most-frequently-changing.

Other choices: `slim` base (smaller size, smaller attack surface), `--no-cache-dir` (pip keeps no download cache).

### Key commands

```bash
docker build -t devops-app:v1 .
docker run -d -p 8090:5000 --name myapp devops-app:v1
docker ps                    # running containers
docker ps -a                 # includes stopped/created containers
docker logs myapp            # stdout/stderr
docker exec -it myapp bash   # shell inside the running container
docker stop / start / rm -f  # lifecycle
```

`-p 8090:5000` maps **host:container** — a common gotcha; only the host side must be free.

### Interview questions

1. Container vs VM? (kernel sharing vs hardware virtualization)
2. Image vs container? (template vs running instance + writable layer)
3. Why does Dockerfile instruction order matter? (layer caching)
4. `CMD` vs `ENTRYPOINT`? (default, overridable args vs fixed executable)
5. In `-p 8090:5000`, which side is the host? (the left)
6. How do you reduce image size? (slim/alpine base, multi-stage builds, `--no-cache-dir`, fewer layers, `.dockerignore`)
7. What is `.dockerignore`? (excludes files from the build context)

---

## Day 2 — Docker Compose (App + Postgres + Redis)

### Concepts

Running one container by hand is fine; running several that must network, share data, and start in order is not. **Docker Compose** declares a multi-container app in one `compose.yaml` and brings it up with one command — the first taste of **infrastructure as code**.

- **Networking** — Compose creates a private network; containers reach each other **by service name** as a hostname, resolved by Docker's internal DNS. This is service discovery.
- **Volumes** — containers are ephemeral; a **named volume** stores data outside the container lifecycle so it survives restarts and removals. This is the answer to "how do you persist data in Docker?"
- **Startup order** — `depends_on` controls start order but does **not** wait for a service to be *ready* to accept connections. True readiness needs healthchecks or app-side retries.

### The compose file (shape)

Three services: `web` (built from the Dockerfile), `db` (official `postgres:16`, with a `pgdata` named volume mounted at `/var/lib/postgresql/data`), and `cache` (official `redis:7`). The app reads all connection info from **environment variables** — the **12-factor** principle: config from the environment, never hardcoded.

### Key commands

```bash
docker compose up -d --build     # build + start everything
docker compose ps                # service status
docker compose logs web          # logs for one service
docker compose exec web ping db  # prove name resolution
docker compose down              # stop + remove containers, KEEP volumes
docker compose down -v           # also DELETE volumes
```

### Proving it works

- `/db` returns the Postgres version → app reached Postgres by the hostname `db`.
- `/visits` increments on each call → app reached Redis by the hostname `cache`, and Redis holds state.
- Persistence demo: Redis (no volume) resets its counter after `down`/`up`; Postgres data survives because of the named volume.

### Interview questions

1. How do Compose services communicate? (private network, by service name via DNS)
2. Named volume vs bind mount? (Docker-managed storage vs host-directory mapping)
3. Does `depends_on` wait for readiness? (No — only for start; use healthchecks/retries)
4. How do you persist database data? (named volume at the data directory)
5. `docker compose down` vs `down -v`? (keeps vs deletes volumes)
6. Where should config/secrets come from? (environment — 12-factor)
7. `build:` vs `image:` in a service? (build from Dockerfile vs pull prebuilt)

---

## Day 3 — CI/CD with GitHub Actions

### Concepts

- **CI (Continuous Integration)** — every push is checked out, tested, and built automatically; the codebase stays buildable and tested.
- **CD (Continuous Delivery/Deployment)** — extends CI by packaging the result (build + push image) and either making it ready to release (*delivery*) or releasing it automatically (*deployment*).
- **GitHub Actions hierarchy:** **workflow → jobs → steps**. Workflows run on **events**; each **job** runs on a fresh **runner** (clean VM); steps run commands or reusable **actions**.

### The pipeline

A `.github/workflows/ci.yaml` with two jobs:

1. **test** — checkout, set up Python, install dependencies, run `pytest`.
2. **build-and-push** — `needs: test` (a gate: only runs if tests pass), logs in to GHCR with the auto-provided `secrets.GITHUB_TOKEN`, then builds and pushes the image.

Key ideas: `needs:` is the gate that stops broken code from being shipped; `secrets.GITHUB_TOKEN` shows that credentials are referenced from a secret store, **never hardcoded**.

### The test

`test_app.py` uses Flask's in-process **test client** to hit `/health` and `/` — fast, no server or database required. Good unit tests avoid hard external dependencies.

### Interview questions

1. CI vs CD, and Delivery vs Deployment?
2. What triggers a pipeline? (events — push, PR, schedule, manual)
3. Workflow → job → step hierarchy? (each job = fresh runner)
4. How do you stop bad code from deploying? (test gate — `needs:`, required checks)
5. How are secrets handled in CI? (secret store, referenced as variables)
6. Why run tests in CI if they pass locally? (clean, reproducible environment; catches "works on my machine")
7. What is an image registry and why push to one? (central versioned storage bridging CI and CD)

---

## Day 4 — Artifact Management: Registries & Nexus OSS

### Concepts

An **artifact** is any built, deployable output (Docker image, `.jar`, npm package, wheel). An **artifact repository / registry** is the central, versioned store — the **bridge between CI and CD**. Its golden rule: **build once, deploy everywhere** — build the image one time, then promote the *identical* bytes through dev → staging → prod. Rebuilding per environment risks drift.

- **Registry vs repository** — a registry hosts many repositories; each repository holds the tags of one artifact.
- **Tag** — a version label (`latest`, `1.0.0`, a git SHA).
- **Immutability** — a published version should never be overwritten; `1.0.0` always means the same bytes.
- **Repository types (Nexus):** **hosted** (your own artifacts), **proxy** (caches an upstream public source), **group** (one URL combining several).

### Part A — GHCR (cloud registry)

```bash
# log in (token piped via stdin, never typed inline)
$env:CR_PAT | docker login ghcr.io -u <username> --password-stdin

docker tag devops-app:v1 ghcr.io/<username>/devops-app:v1
docker push ghcr.io/<username>/devops-app:v1
docker pull ghcr.io/<username>/devops-app:v1
```

`docker tag` adds a second name to the same image ID (no copy). `docker push` uploads layers individually and skips ones the registry already has. The token needs the **`write:packages`** scope (a *classic* token, not fine-grained), and the namespace in the path must be **your** username.

### Part B — Tagging strategy

Deploying `latest` is dangerous: it is mutable and points to whatever was pushed last, so it is not reproducible and cannot be reliably rolled back. Production should deploy **immutable, specific tags** (`1.0.0` or a git commit SHA) so a deployment always refers to exact, unchanging bytes.

```bash
docker tag devops-app:v1 ghcr.io/<username>/devops-app:1.0.0
docker push ghcr.io/<username>/devops-app:1.0.0
```

### Part C–E — Nexus OSS (self-hosted registry)

Many companies self-host artifact storage for control, security, air-gapped networks, or dependency caching. Nexus OSS is the free standard and runs in a container. **Both** the UI port and the registry connector port must be **published** at run time:

```bash
docker run -d -p 8081:8081 -p 8082:8082 --name nexus sonatype/nexus3
docker exec nexus cat /nexus-data/admin.password   # initial admin password
```

Then in the UI (http://localhost:8081): create a **docker (hosted)** repository with an HTTP connector on **8082**. Because that connector is plain HTTP, Docker must be told to allow it via Docker Engine config:

```json
{ "insecure-registries": ["localhost:8082"] }
```

(This is a local-dev shortcut; production registries use TLS.) Then:

```bash
docker login localhost:8082
docker tag devops-app:v1 localhost:8082/devops-app:1.0.0
docker push localhost:8082/devops-app:1.0.0
```

### Interview questions

1. What is an artifact and an artifact repository? (built output; versioned store bridging CI and CD)
2. "Build once, deploy everywhere" — meaning and why? (promote identical bytes; rebuilding risks drift)
3. Registry vs repository?
4. Why is deploying `latest` dangerous? (mutable, non-reproducible; use version/SHA tags)
5. Hosted vs proxy vs group repository?
6. Why self-host Nexus/Artifactory? (control, security, air-gap, dependency caching, compliance)
7. What does `docker tag` actually do? (adds a name to the same image ID — no copy)
8. How should credentials reach `docker login` in automation? (`--password-stdin` / secret store, never inline)

---

## Day 5 — Kubernetes Core: Pods, Deployments, Services

### Concepts — why Kubernetes exists

Docker runs containers; **Kubernetes orchestrates them** across a cluster of machines — running many copies, restarting crashed ones, replacing them without downtime, scaling under load, and providing a stable network address even as containers come and go.

The core mental model: **Kubernetes is declarative.** You do not say "start this container" (imperative). You declare the *desired state* ("I want 3 copies running") and Kubernetes continuously works to make actual state match. This **reconciliation loop** is the heart of Kubernetes — if a pod dies, it notices desired (3) ≠ actual (2) and creates a replacement.

### The objects

- **Pod** — smallest deployable unit; wraps one or more containers sharing network and storage. Pods are **ephemeral and disposable**: created, destroyed, and replaced constantly, each with a new IP. Never rely on a specific pod.
- **Deployment** — the object you actually use. Maintains a desired replica count, handles rolling updates, recreates dead pods. Creates a **ReplicaSet** that does the pod-counting.
- **Service** — a stable network endpoint (fixed name/IP) that load-balances across matching pods. It finds pods via **label selectors**, not IPs — which is why it survives pod replacement.

Relationship: **Deployment manages Pods; Service routes traffic to Pods via labels.**

### Cluster setup (Minikube + kubectl)

```bash
minikube start --driver=docker
kubectl get nodes          # expect one node, status Ready
kubectl cluster-info
```

`kubectl` talks to the cluster's API server (the front door to Kubernetes) via a kubeconfig file.

### Making the image reachable by the cluster

Minikube cannot see the host's local Docker images by default. Two options:

- **Option A** — use the public GHCR image (`ghcr.io/<username>/devops-app:v1`), after setting the package visibility to **Public** in GitHub Packages.
- **Option B** — `minikube image load devops-app:v1` to copy the local image into the cluster (add `imagePullPolicy: IfNotPresent`).

### Deployment manifest (`k8s/deployment.yaml`)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: devops-app
  labels:
    app: devops-app
spec:
  replicas: 3                      # desired state: 3 identical pods
  selector:
    matchLabels:
      app: devops-app              # this Deployment manages pods with this label
  template:
    metadata:
      labels:
        app: devops-app            # pod label MUST match the selector above
    spec:
      containers:
        - name: devops-app
          image: ghcr.io/<username>/devops-app:v1
          ports:
            - containerPort: 5000
          livenessProbe:           # restart the pod if this fails
            httpGet:
              path: /health
              port: 5000
            initialDelaySeconds: 5
            periodSeconds: 10
          readinessProbe:          # no traffic until this passes
            httpGet:
              path: /health
              port: 5000
            initialDelaySeconds: 3
            periodSeconds: 5
```

The label linkage (`selector.matchLabels` = `template.metadata.labels`) is how the Deployment knows which pods it owns — a common interview question. The `/health` endpoint from Day 1 now powers the probes.

**Liveness vs readiness:** liveness = *should this pod be restarted?*; readiness = *should this pod receive traffic?* This is the proper solution to the "readiness" gap that `depends_on` could not solve in Day 2.

### Service manifest (`k8s/service.yaml`)

```yaml
apiVersion: v1
kind: Service
metadata:
  name: devops-app-service
spec:
  type: NodePort
  selector:
    app: devops-app                # routes to pods with this label
  ports:
    - port: 80                     # the service's own port
      targetPort: 5000             # container port to forward to
```

**Service types to know:**

- **ClusterIP** (default) — reachable only inside the cluster (e.g. internal databases).
- **NodePort** — opens a port on the node for external access; good for local testing.
- **LoadBalancer** — provisions an external cloud load balancer; for production on cloud.

### Applying and observing

```bash
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl get deployments
kubectl get pods                   # watch ContainerCreating -> Running
kubectl get services
```

`ImagePullBackOff` almost always means the GHCR package is not public, or the image name is wrong.

### Self-healing demo (the one that sells Kubernetes)

```bash
kubectl get pods
kubectl delete pod <pod-name>
kubectl get pods                   # a NEW replacement pod appears within seconds
```

Deleting a pod drops actual state to 2 while desired is 3, so the Deployment immediately creates a replacement — the reconciliation loop, demonstrated.

### Reaching the app + load balancing

```bash
minikube service devops-app-service --url
curl.exe <printed-url>             # refresh repeatedly
```

The `hostname` field in the JSON rotates across the three pods — visual proof the Service is load-balancing.

### Essential debugging commands

```bash
kubectl describe pod <pod-name>    # status + Events (why it failed) — primary debug tool
kubectl logs <pod-name>            # application logs
kubectl exec -it <pod-name> -- bash
kubectl get all
```

Debugging a stuck pod: `kubectl describe pod` (read the Events) → `kubectl logs` (application errors).

### Scaling

```bash
kubectl scale deployment devops-app --replicas=5
```

Change the desired number; Kubernetes reconciles. In production you edit the YAML (declarative, version-controlled) rather than using imperative `scale`.

### Interview questions

1. Why Kubernetes over plain Docker? (orchestration: scaling, self-healing, rolling updates, stable networking)
2. What do "declarative" and the reconciliation loop mean?
3. Pod vs Deployment vs ReplicaSet?
4. Why are pods ephemeral? (constant recreation, new IP each time)
5. How does a Service find its pods? (label selectors, not IPs)
6. ClusterIP vs NodePort vs LoadBalancer?
7. Liveness vs readiness probe? (restart-me vs send-me-traffic)
8. How do you debug a failing pod? (`describe` → Events, then `logs`)
9. How does Kubernetes self-heal? (reconciliation replaces dead pods)

---

## Cross-cutting lessons learned (the debugging that taught the most)

Real environment friction produced the most transferable lessons:

- **A failed `docker run` still leaves a created container behind**, blocking the name. `docker ps -a` reveals it; plain `docker ps` does not.
- **Port conflicts and reachability are about the host side of `-p`.** "The service is running but I can't connect" almost always means the port was never *published* to the host (e.g. Nexus listening on 8082 internally with no `-p 8082:8082`).
- **A 404 vs a connection error mean different things.** "Not Found" = the app answered but the route is missing (application-level). "Connection refused/timed out" = nothing is listening (container/network level).
- **Stale layer cache serves old code.** After editing source, `docker compose build --no-cache` guarantees the new code is baked in.
- **The container's environment is separate from the host's.** Flask installed in the container says nothing about the host Python — the exact problem containers exist to eliminate. This surfaced sharply on Python 3.14, where `psycopg2-binary` had no prebuilt wheel and failed to compile, while the container's pinned Python 3.12 built it cleanly. Lesson: pin versions and rely on a defined base image for reproducibility.
- **Top-level imports run at module load.** Moving optional imports (`psycopg2`, `redis`) into the route functions that use them (lazy imports) keeps the app bootable and tests fast in minimal environments.
- **Authentication vs authorization.** "Login succeeded" proves identity, not permission. A push denied with a valid login points to a missing scope (`write:packages`) or the wrong namespace — not bad credentials.
- **Watch for placeholders.** `YOUR_USERNAME`, `<token>`, `example.com` are always meant to be replaced; pasting them literally is a common source of confusing errors.

---

*Next: Day 6 — Kubernetes advanced (ConfigMaps, secrets, ingress, scaling, rolling updates) and Day 7 — the full capstone pipeline (GitHub → CI → registry → Kubernetes) plus interview prep.*