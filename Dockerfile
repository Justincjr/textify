FROM ubuntu

# Install Python and pip
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv

# Set the working directory
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Create and activate a virtual environment
RUN python3 -m venv venv

# Install the Python dependencies
RUN venv/bin/pip install --upgrade pip
RUN venv/bin/pip install -r requirements.txt

EXPOSE 5000

ENV key=2efd329bd21447f5b0d9aedde957916d
ENV region=eastus
ENV api_key=d579c5a573954baa9af447437e073882
ENV azure_endpoint=
ENV deployment=
ENV email_username=
ENV email_password=
ENV sender_email=

CMD ["/app/venv/bin/gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "50", "flask_server:app"]