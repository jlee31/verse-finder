# Quote Finder

a web application that uses RAG to identify useful quotes, with an agent that puts it altogether

## to run 

```bash
git clone https://github.com/jlee31/verse-finder.git
cd verse-finder
cp backend/.env.example backend/.env    # then paste your key in
```

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000
```

docker:

```bash
docker build -t verse-finder .
docker run --rm -p 8000:8000 --env-file backend/.env verse-finder
```

### deployed on railway

```link
https://quote-finder-production.up.railway.app/
```
