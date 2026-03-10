# GreenScope — Scope 3 ESG Reporting

Full-stack app: FastAPI + PostgreSQL backend, React frontend.
Deploys to **Railway** (backend + DB) + **Vercel** (frontend) with GitHub Actions CI/CD.

---

## Project Structure

```
greenscope/
├── .github/workflows/deploy.yml   ← CI/CD pipeline
├── backend/
│   ├── main.py                    ← FastAPI app + PostgreSQL
│   ├── requirements.txt
│   ├── railway.toml               ← Railway deploy config
│   └── render.yaml                ← Render deploy config (alternative)
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── pages/
│   │   └── lib/api.js
│   ├── package.json
│   ├── vite.config.js
│   └── vercel.json                ← Vercel deploy config
└── .gitignore
```

---

## Local Development

### 1. PostgreSQL

You need a local Postgres instance. Easiest options:

**Option A — Docker (recommended):**
```bash
docker run -d \
  --name greenscope-pg \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=greenscope \
  -p 5432:5432 \
  postgres:16
```

**Option B — Install Postgres directly:**
- Mac: `brew install postgresql@16 && brew services start postgresql@16`
- Ubuntu: `sudo apt install postgresql && sudo systemctl start postgresql`
- Windows: Download from https://postgresql.org/download/windows/

Then create the DB:
```bash
psql -U postgres -c "CREATE DATABASE greenscope;"
```

---

### 2. Backend

```bash
cd backend

python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

pip install -r requirements.txt

# Create .env file
cat > .env << EOF
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/greenscope
FRONTEND_URL=http://localhost:3000
EOF

uvicorn main:app --reload --port 8001
```

Tables are auto-created on first run. Open **http://localhost:8001/docs** for Swagger UI.

---

### 3. Frontend

```bash
cd frontend

npm install

# Create .env.local (leave empty for local dev — Vite proxy handles it)
touch .env.local

npm run dev
```

Open **http://localhost:3000**

---

## Deployment

### Step 1 — Push to GitHub

```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/greenscope.git
git push -u origin main
```

---

### Step 2 — Deploy Backend to Railway

1. Go to **railway.app** → New Project → Deploy from GitHub repo
2. Select your repo → select the `backend/` folder as root
3. Railway will auto-detect Python and use `railway.toml`
4. Add **PostgreSQL** plugin:
   - Click `+ New` → Database → Add PostgreSQL
   - Railway auto-sets `DATABASE_URL` in your service env vars
5. Add env variable: `FRONTEND_URL` = `https://your-app.vercel.app` (you'll get this in step 3)
6. Copy your Railway backend URL — looks like `https://greenscope-backend.up.railway.app`

**Railway is free for $5/month credit (enough for this).**

---

### Step 3 — Deploy Frontend to Vercel

1. Go to **vercel.com** → New Project → Import GitHub repo
2. Set **Root Directory** to `frontend`
3. Add environment variable:
   - `VITE_API_URL` = `https://greenscope-backend.up.railway.app` (your Railway URL)
4. Deploy → get your Vercel URL like `https://greenscope.vercel.app`
5. Go back to Railway → update `FRONTEND_URL` to your Vercel URL

---

### Step 4 — Set up GitHub Actions CI/CD

Add these secrets to your GitHub repo (Settings → Secrets → Actions):

| Secret | How to get it |
|--------|---------------|
| `RAILWAY_TOKEN` | Railway dashboard → Account → Tokens → New Token |
| `VITE_API_URL` | Your Railway backend URL |
| `VERCEL_TOKEN` | vercel.com → Settings → Tokens → Create |
| `VERCEL_ORG_ID` | Run `vercel whoami` and check `.vercel/project.json` after first deploy |
| `VERCEL_PROJECT_ID` | Same `.vercel/project.json` file |

After adding secrets — every push to `main` automatically:
1. Runs backend smoke tests against a test Postgres
2. Builds the frontend
3. Deploys backend to Railway
4. Deploys frontend to Vercel

---

## Alternative: Deploy Backend to Render (also free)

1. Go to **render.com** → New → Web Service → Connect GitHub
2. Set Root Directory to `backend`
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Add PostgreSQL: New → PostgreSQL → copy Internal Database URL
6. Add env var: `DATABASE_URL` = the internal DB URL from above

Render's free tier spins down after 15 min inactivity (cold start ~30s).
Railway has no cold starts on paid tier.

---

## Environment Variables Reference

### Backend
| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://user:pass@host/db` |
| `FRONTEND_URL` | Your Vercel URL (for CORS) | `https://greenscope.vercel.app` |

### Frontend
| Variable | Description | Example |
|----------|-------------|---------|
| `VITE_API_URL` | Your Railway/Render backend URL | `https://greenscope-backend.up.railway.app` |

---

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check |
| POST | `/api/entries` | Add emission entry |
| GET | `/api/entries?year=2024` | Get all entries |
| DELETE | `/api/entries/{id}` | Delete entry |
| GET | `/api/dashboard?year=2024` | Dashboard stats |
| POST | `/api/calculate/preview` | Preview without saving |
| GET | `/api/factors` | All emission factors |
| POST | `/api/suppliers` | Add supplier |
| GET | `/api/suppliers` | List suppliers |

Full interactive docs at `/docs` (Swagger UI).

---

## Common Issues

**`asyncpg` connection error:**
Make sure `DATABASE_URL` uses `postgresql+asyncpg://` not `postgresql://`
The backend auto-fixes `postgres://` (Railway format) but double-check.

**CORS errors in production:**
Set `FRONTEND_URL` in Railway/Render env vars to your exact Vercel URL.

**Vercel build fails:**
Make sure `VITE_API_URL` secret is set in GitHub Secrets before the workflow runs.

**Railway deploy not triggering:**
Make sure `RAILWAY_TOKEN` secret is correct and the service name in `deploy.yml` matches your Railway service name.
