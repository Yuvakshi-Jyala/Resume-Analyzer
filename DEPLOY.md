# Deploying the Resume Screening UI

Two free services: **Render** (backend) + **Vercel** (frontend).

## 0. Push to GitHub first
From the `ui` folder:

    git init
    git add .
    git commit -m "Resume screening UI"
    git branch -M main
    git remote add origin https://github.com/<you>/<repo>.git
    git push -u origin main

The `.gitignore` keeps your `.env` (with the CogitX secret) OUT of the repo. Verify:
`git status` should NOT list backend/.env.

## 1. Backend on Render
1. render.com -> New -> Web Service -> connect your GitHub repo
2. Render detects `render.yaml`. It sets root=backend, start=uvicorn.
3. Add environment variables (Render dashboard -> Environment):
   - COGITX_BASE_URL      = https://cpab.cogitx.ai/project
   - COGITX_EXPORT_ID     = 6a672a6829131252a1f96bdc
   - COGITX_CLIENT_ID     = <your client id>
   - COGITX_CLIENT_SECRET = <your client secret>
   - FRONTEND_ORIGINS     = (fill in AFTER step 2, with the Vercel URL)
4. Deploy. Note the backend URL, e.g. https://resume-screening-backend.onrender.com

## 2. Frontend on Vercel
1. vercel.com -> New Project -> import the same GitHub repo
2. Vercel reads `vercel.json` (build = frontend, output = frontend/dist)
3. Add environment variable (Vercel -> Settings -> Environment Variables):
   - VITE_API_URL = <your Render backend URL from step 1>
4. Deploy. Note the frontend URL, e.g. https://resume-screening.vercel.app

## 3. Connect them
1. Back in Render, set FRONTEND_ORIGINS = <your Vercel URL>
   (comma-separate if more than one)
2. Render redeploys. Done.

## 4. Share
Send the Vercel URL to Akash & Ashika.

## Notes
- Render free tier SLEEPS after ~15 min idle. First hit after sleep takes
  ~30-60s to wake. Open the link yourself a minute before a demo, or the
  first screening will look slow.
- To update: push to GitHub -> both services auto-redeploy.
