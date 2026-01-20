# Base image - Python 3.11
FROM python:3.11-slim
# Set working directory inside container
WORKDIR /app
# Copy requirements first (for caching)
COPY requirements.txt .
# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt
# Copy your application code
COPY . .
# Copy ML files (embeddings and quotes)
COPY ../ml/quote_embeddings_mpnet.npy ./ml/
COPY ../ml/quotes_list.json ./ml/
# Tell Docker what port the app uses
EXPOSE 8000
# Command to run when container starts
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]