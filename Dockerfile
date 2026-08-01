# Dockerfile — tells Hugging Face Spaces how to build and run the agent.
# HF Spaces (Docker type) builds this image and runs the container for you.

FROM python:3.11-slim

# HF Spaces runs the container as a non-root user with uid 1000 by convention.
# Creating that user ourselves keeps file permissions sane.
RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH"

WORKDIR /app

# Install dependencies first so Docker can cache this layer (faster rebuilds
# when only your code changes, not your requirements).
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of the app in.
COPY --chown=user . .

# HF Spaces expects your web app to listen on port 7860.
EXPOSE 7860
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "7860"]
