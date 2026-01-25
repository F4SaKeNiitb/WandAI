# WandAI Coolify Deployment - Separate Services

## Quick Setup Guide

### 1. Backend Service

**In Coolify Dashboard:**

1. Click **"New Resource"** → **"Application"**
2. **Source**: 
   - Select **"Public Repository"** or connect your GitHub account
   - Repository: `https://github.com/F4SaKeNiitb/WandAI.git`
   - Branch: `main`
3. **Build Pack**: `Dockerfile`
4. **Base Directory**: `backend`
5. **Dockerfile Location**: `Dockerfile` (relative to base directory)
6. **Port**: `8000`
7. **Environment Variables** (click "Add Variable"):
   ```
   GEMINI_API_KEY=<your-gemini-key>
   TAVILY_API_KEY=<your-tavily-key>
   HOST=0.0.0.0
   PORT=8000
   ```
8. **Persistent Storage** (Optional but recommended):
   - Add Volume: `/app/checkpoints.db`
   - This preserves your workflow state between deployments
9. **Domain**: Assign a domain (e.g., `api-wandai.yourdomain.com`)
10. Click **"Deploy"**

### 2. Frontend Service

**In Coolify Dashboard:**

1. Click **"New Resource"** → **"Application"**
2. **Source**: 
   - Repository: `https://github.com/F4SaKeNiitb/WandAI.git`
   - Branch: `main`
3. **Build Pack**: `Dockerfile`
4. **Base Directory**: `frontend`
5. **Dockerfile Location**: `Dockerfile`
6. **Port**: `80`
7. **Build Arguments** (if needed):
   - Click "Add Build Argument"
   - `VITE_API_URL=https://api-wandai.yourdomain.com` (your backend URL from step 1)
8. **Domain**: Assign a domain (e.g., `wandai.yourdomain.com`)
9. Click **"Deploy"**

### 3. Enable SSL

Coolify automatically provisions Let's Encrypt SSL certificates. Just ensure:
- Both domains are properly configured in your DNS
- Point A records to your Coolify server IP

### 4. Test Your Deployment

1. Visit your frontend URL: `https://wandai.yourdomain.com`
2. Submit a test request
3. Check logs in Coolify if anything fails

## Important Notes

- **CORS**: The backend already has CORS configured for `*`. In production, you may want to restrict this to your frontend domain only.
- **WebSocket**: Make sure both frontend and backend use HTTPS (not mixed HTTP/HTTPS) for WebSocket connections to work.
- **Database**: The `checkpoints.db` file stores workflow state. Without persistent storage, you'll lose session data on redeploy.

## Troubleshooting

### Backend Issues
- Check Coolify logs for Python errors
- Verify all environment variables are set
- Ensure port 8000 is exposed

### Frontend Issues
- Check browser console for API connection errors
- Verify `VITE_API_URL` build argument was correct during builds
- Ensure CORS is enabled on backend

### WebSocket Connection Fails
- Verify both services use HTTPS
- Check nginx proxy configuration
- Ensure `/ws` endpoint is accessible

## Next Steps

After successful deployment:
1. Test all features (planning, execution, chat)
2. Monitor logs for errors
3. Set up monitoring/alerts in Coolify
4. Configure backups for `checkpoints.db`
