FROM python:3.7-slim-buster

# This is to install gcc, etc. that's needed by Airflow.
RUN export DEBIAN_FRONTEND=noninteractive && \
  apt-get update && apt-get -y upgrade && \
  apt-get -y install --no-install-recommends gcc python3-dev build-essential && \
  apt-get clean && \
  rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip

RUN useradd -m airflow
WORKDIR /home/airflow

ENV AIRFLOW_HOME /home/airflow

COPY requirements.txt .
RUN pip install -r requirements.txt

USER airflow

ENTRYPOINT []
CMD []
