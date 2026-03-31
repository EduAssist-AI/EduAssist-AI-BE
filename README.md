# EduAssist-AI-BE
Backend application for Education assistance mainly to help summarize video Lectures, Slides and Docs

## 🚀 Quick Start

### Local Development

1. **Clone the repository:**
    ```bash
    git clone https://github.com/your-username/EduAssist-AI-BE.git
    cd EduAssist-AI-BE
    ```

2. **Create and activate virtual environment:**
    ```bash
    # Windows
    python -m venv venv
    .\venv\Scripts\activate

    # macOS/Linux
    python3 -m venv venv
    source venv/bin/activate
    ```

3. **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4. **Install Ollama** (required for LLM inference):
    - Download from: https://ollama.com/
    - Pull the model: `ollama pull llama2`

5. **Run the application:**
    ```bash
    uvicorn app.main:app --reload --port 8000 --host 127.0.0.1
    ```

---

## 🌐 Deployment Options

### Option 1: Cloudflare Tunnel (Recommended for Portfolio/Demos)

**Best for:** Live demos, interviews, testing - **FREE**, more reliable than ngrok

#### Setup
```bash
# Step 1: Start backend (in terminal 1)
uvicorn app.main:app --reload --port 8000 --host 127.0.0.1

# Step 2: Start Cloudflare tunnel (in terminal 2)
cloudflared tunnel --url http://localhost:8000
```

**Note:** Install cloudflared from https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/

Or use the npm version:
```bash
npx cloudflared tunnel --url http://localhost:8000
```

#### Update `.env.production`
Copy the tunnel URL (e.g., `https://xxxx.trycloudflare.com`) to `.env.production`:
```env
VITE_API_URL=https://your-tunnel-url.trycloudflare.com
```

**Important:**
- Keep the tunnel running while testing
- URL changes each time you restart
- No account required for free tier

---

### Option 2: Docker (Local/Cloud)

**Best for:** Consistent environments, cloud deployment

#### Run with Docker Compose
```bash
docker-compose up --build
```

This starts:
- Backend service (port 8000)
- MongoDB (port 27017)
- Ollama (port 11434)

---

### Option 3: Render (Cloud Hosting)

**Best for:** Always-on production deployment

1. Create account at https://render.com
2. Connect your GitHub repository
3. Use the provided `render.yaml` configuration
4. Add environment variables:
   - `MONGODB_URL` (use MongoDB Atlas free tier)
   - `JWT_SECRET` (auto-generated)
   - `GOOGLE_DRIVE_CREDENTIALS_PATH`

**Note:** For LLM inference, use external APIs (OpenAI/HuggingFace) as Render's free tier doesn't support Ollama efficiently.

---

### Option 4: AWS EC2

**Best for:** Full control, scalable production

Recommended instances:
- **t3.large** (2 vCPU, 8GB RAM) - ~$60/month - Minimum for Llama2
- **t3.xlarge** (4 vCPU, 16GB RAM) - ~$120/month - Recommended

---

## 📁 Project Structure

```
EduAssist-AI-BE/
├── app/
│   ├── main.py           # FastAPI application
│   ├── config.py         # Configuration settings
│   ├── tasks.py          # Celery tasks
│   ├── db/               # Database models & connections
│   ├── rag/              # RAG (Retrieval-Augmented Generation)
│   ├── routes/           # API route handlers
│   └── utils/            # Utility functions
├── chroma_db/            # Vector database storage
├── uploads/              # Uploaded files
├── .env.production       # Production environment variables
├── docker-compose.yml    # Docker configuration
└── render.yaml           # Render deployment config
```

---

## 🔧 Environment Variables

Create a `.env` file with:

```env
MONGODB_URL=mongodb://localhost:27017
DB_NAME=eduassist_db
JWT_SECRET=your-secret-key
GOOGLE_DRIVE_CREDENTIALS_PATH=credentials.json
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama2
```

---

## 🧪 Testing

```bash
# Run tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html
```

---

## 📝 API Documentation

Once running, access:
- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc
- **Health Check:** http://localhost:8000/health

---

## 🛠️ Troubleshooting

### Ollama not working
```bash
# Check if Ollama is running
ollama list

# Pull Llama2 model
ollama pull llama2

# Restart Ollama service
```

### Port already in use
```bash
# Kill process on port 8000 (Windows)
netstat -ano | findstr :8000
taskkill /PID <PID> /F
```

### MongoDB connection error
- Ensure MongoDB is running: `mongod --dbpath <path>`
- Or use MongoDB Atlas free tier

### Tunnel connection issues
- Try Cloudflare Tunnel instead of ngrok (more reliable)
- Check firewall settings
- Ensure backend is running before starting tunnel

---

## 📄 License

MIT License

---

## 👨‍💻 Author

Created for educational assistance and portfolio showcase.
