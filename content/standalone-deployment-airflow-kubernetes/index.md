+++
title = "Standalone deployment of Airflow on Kubernetes"
date = 2022-07-02
+++

We will show how to do a very simple standalone production deployment of Airflow on Kubernetes.

- _Simple_: it's just a Kubernetes spec that runs one Airflow instance.
- _Standalone_: we deploy Airflow together with its database.
- _Production_: works well on production (with some limitations).

The idea is to have a single Kubernetes Pod of two containers: one Postgres and one Airflow.
To make the Postgres DB persistent, we deploy this with a StatefulSet and a PersistentVolumeClaim.
This way we don't lose progress when we restart Airflow in the middle of executing a DAG.

# Why?

This should work everywhere where Kubernetes is available.
It has multiple advantages.

- **Minimal DB management.**
  We have the database in the same Pod as Airflow.
  It's packaged together, we don't need to do much with it.
- **Easy deployment of DAGs.**
  We just build a new Docker image that packages our Airflow code, push it to an image registry, and change the image version in the Kubernetes spec.
  In our organization we probably have other services running on Kubernetes.
  We deploy Airflow code the same way, no need for special code syncing logic.
- **Reproducible local development.**
  We can replicate the same setup locally, no need to access a remote DB.
  See in another blog post [how to set up local development with Kuberenetes](@/local-development-kubernetes/index.md).

Of course, there's a price to pay for this simplicity.

# Limitations

This is intended for folks that don't want to scale horizontally: we will have one instance, it won't be highly available, and we might lose DB state.
This sounds scary, but if we already follow the best-practices, it should not be a problem at all. 

- **Only one instance: does not scale.**
  We can add higher amount of resources (CPU, memory), but only as much as the Kubernetes cluster allows (probably depending on biggest node in the cluster).
  This solution by design does not scale to multiple instances.
  That said, one instance should have enough resources in most use-cases: Airflow should only orchestrate, the real heavy-lifting should run elsewhere.
- **Not highly available: restart will make tasks fail.**
  This should be okay if we run the heavy-lifting elsewhere and tasks can resume.
  We won't lose the complete DAG progress, because we persist the Airflow DB.
  E.g. if [we only use KubernetesPodOperator](https://medium.com/bluecore-engineering/were-all-using-airflow-wrong-and-how-to-fix-it-a56f14cb0753) the actual heavy-lifting will continue in that separate Kubernetes Pod while we restart Airflow.
  Then, after Airflow has restarted, the KubernetesPodOperator will re-attach to the already running Pod.
- **Might lose DB state.**
  We don't backup the Postgres DB, so we might lose all the data there if the persistent volume where we store Postgres data is lost (in a very improbable scenario).
  This is not really a problem if we don't rely on Airflow DAG history: we don't do backfills, a single DAG run will fill up history if needed.
  It's a good practice regardless not to rely on Airflow DAG history.

So, let's make sure that
- we have enough resources for Airflow,
- we only use resumable Airflow Operators, and
- we don't rely on DAG history.

# How?

Just to try this setup it's useful to [set up local development with Kuberenetes](@/local-development-kubernetes/index.md) first.

We're going to use Airflow 1.x, but this should work similarly with Airflow 2.x.

## Base image

Let's assume we have a Docker registry running at `localhost:5000`. (In real life it might be something like `gcr.io`.)

We should have an Airflow base Docker image that only has Airflow.
We can use the [official Airflow image](https://hub.docker.com/r/apache/airflow) or we can build our own.
To build our own, we will need these two files:

<details>
<summary>View Dockerfile</summary>

```Dockerfile
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

COPY base-image/requirements.txt .
RUN pip install -r requirements.txt

USER airflow

ENTRYPOINT []
CMD []

### from here on app specific

COPY dags dags
```
</details>

<details>
<summary>View requirements.txt</summary>

```requirements.txt
# This is what we actually want to install.
apache-airflow[gcp,kubernetes]==1.10.15
# This is needed for Postgres connection
psycopg2-binary

# But there are breaking changes in some transitive dependencies
# so we need to pin them.
# See https://github.com/pallets/markupsafe/issues/284
markupsafe>=2.0.1,<2.1.0
# See https://stackoverflow.com/questions/69879246/no-module-named-wtforms-compat
wtforms>=2.3.3,<2.4.0
# See https://github.com/sqlalchemy/sqlalchemy/issues/6065
sqlalchemy>=1.3.20,<1.4.0
# See https://itsmycode.com/importerror-cannot-import-name-json-from-itsdangerous/
itsdangerous>=2.0.1,<2.1.0
```
</details>

And execute
```sh
docker build -t localhost:5000/airflow:latest .
```

## Building an image with our code

Let's say we have a very simple dummy DAG in `dags/dummy.py`:

```python
from airflow import DAG
from airflow.utils import timezone
from airflow.operators.dummy_operator import DummyOperator

dag = DAG(
    dag_id="dummy",
    schedule_interval=None,
    catchup=False,
    default_args=dict(start_date=timezone.datetime(2022, 1, 1)),
)

DummyOperator(task_id="dummy", dag=dag)
```

We can package this in a Docker image from our base image with this `Dockerfile`:

```Dockerfile
FROM localhost:5000/airflow:latest

COPY dags dags
```

To build and push it:

```sh
docker build -t localhost:5000/dummydag:latest .
docker push localhost:5000/dummydag:latest
```

## Kubernetes deployment with StatefulSet

We can define a Kubernetes [StatefulSet](https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/) with Airflow and Postgres:

- **Airflow and Postgres containers in the same Pod.**
  This makes sure self-contained deployment and they can easily communicate because they are "on the same machine".
- **StatefulSet with a single instance.**
  This gives us easy deploying and restarting very similarly to a [Deployment](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/). 
  The big difference is that StatefulSet also allows us to use persistent storage:
  if a Pod gets killed the restarted Pod will be on the same Node.
- **Persistent Volume mounted to Postgres container.**
  Persistent storage for our Airflow DB to not lose data between deployments.
  Note that we can only use [Persistent Volumes](https://kubernetes.io/docs/concepts/storage/persistent-volumes/) because we use StatefulSet.

We define all of this in a Kubernetes spec file `airflow.yml`:

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: airflow
spec:
  serviceName: "my-airflow-service"
  selector:
    matchLabels:
      my-app-label: airflow-app
  # Claiming a Persistent Volume for our Pod.
  volumeClaimTemplates:
    - metadata:
        name: postgres-volume
      spec:
        # Only one Pod should read and write it.
        accessModes: ["ReadWriteOnce"]
        resources:
          requests:
            storage: 1Gi
  template:
    metadata:
      labels:
        my-app-label: airflow-app
    spec:
      containers:
        # Postgres container with dummy user and password defined.
        - name: postgres
          image: postgres:9
          env:
            - name: POSTGRES_USER
              value: airflow_user
            - name: POSTGRES_PASSWORD
              value: airflow_pass
            - name: POSTGRES_DB
              value: airflow_db
          volumeMounts:
            - name: postgres-volume
              # This is the default path where Postgres stores data.
              mountPath: /var/lib/postgresql/data
        # Airflow container with our code.
        - name: airflow
          # We use the image that we built.
          image: localhost:5000/dummydag:latest
          command: ['/bin/bash',
                    '-c',
                  # We need to start both the Web UI and the scheduler.
                    'airflow upgradedb && { airflow webserver -p 8080 & } && airflow scheduler']
          env:
            - name: AIRFLOW_HOME
              value: '/home/airflow'
            - name: AIRFLOW__CORE__LOAD_EXAMPLES
              value: 'false'
            - name: AIRFLOW__CORE__EXECUTOR
              # Use an executor that can actually run tasks in parallel.
              value: 'LocalExecutor'
            - name: AIRFLOW__CORE__SQL_ALCHEMY_CONN
              # We use the same user and password as defined above.
              value: 'postgresql+psycopg2://airflow_user:airflow_pass@localhost:5432/airflow_db'
```

Then we can deploy it:

```sh
kubectl apply -f airflow.yml
```

And we can see the StatefulSet and Pod.

```sh
kubectl get statefulsets
kubectl get pods
```

We can check Airflow Web UI with port-forwarding:  

```sh
kubectl port-forward pod/airflow-0 8080:8080
```

Then go to http://localhost:8080 to see the Web UI.

# Going further

This is a very basic setup, we can improve it:

- **Deploying new DAGs.**
  How do we add and deploy new code?
  We can create Docker images with different versions (e.g. `localhost:5000/dummydag:123` instead of `localhost:5000/dummydag:latest`) and use them in `airflow.yml` and call `kubectl apply -f airflow.yml` again.
  To automate this, it might require passing the version and templating `airflow.yml`.
  We probably need this in our CI/CD setup.
- **Expose as Service.**
  We could expose the Web UI of Airflow as a [Service](https://kubernetes.io/docs/concepts/services-networking/service/).
- **Store password as a Secret.**
  Currently, we have a very dummy weak password for Postgres.
  We could improve security by generating a (cryptographically secure) random password and storing it as a [Secret](https://kubernetes.io/docs/concepts/configuration/secret/).
- **Use Postgres proxy.**
  Postgres doesn't handle multiple connections well.
  Adding a proxy container such as [pgbouncer](https://www.pgbouncer.org/) can help performance.
