+++
title = "Local development with Kubernetes"
date = 2022-06-27
+++

It's worth investing in local Kubernetes setup if we're using Kubernetes.
It can save a lot of time.

# Why?

Nowadays, Kubernetes is part of development.
E.g. we might tweak [readiness probe](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/) together with [application code](https://www.baeldung.com/spring-liveness-readiness-probes).
Using a local cluster gets us a much faster to development cycle compared to a real cluster. There are many reasons, but there's one big in my experience.

**Building Docker image is slow when using a real cluster**. Every time we make a code change we either need to push code to some CI/CD environment or build Docker image locally and push the image to a remote registry.
- _CI/CD environment_ will be slow because probably there's lot less aggressive Docker caching as locally.
- _Pushing to a remote registry_ will be slow because image sizes (or layers) can be big (even if we optimize it).

# How?

We will set up a
- local Kubernetes cluster where we can use
- local Docker images.

Then use it:
- create a simple script,
- package it into a Docker image,
- run it on our local Kubernetes cluster.

Before we get started, we'll need a Docker Desktop, a terminal, and a text editor.
We use MacOS, but should mostly work on Linux too.

# Setup local Kubernetes cluster

We're going to use [k3d](https://k3d.io/).
It's an easy way to run [k3s](https://github.com/k3s-io/k3s) which is a very lightweight [k8s](https://kubernetes.io/) distribution.
I hope the names are confusing.

Install k3d:
```sh
brew install k3d
```

([See other installation methods](https://k3d.io/) if you're not on MacOS.)

Create cluster including local Docker image registry [for being able to use local images](https://github.com/k3d-io/k3d/issues/19):

```sh
k3d registry create registry.localhost --port 5000
k3d cluster create mycluster \
  --registry-use k3d-registry.localhost:5000 \
  --registry-config <(echo '{"mirrors":{"localhost:5000":{"endpoint":["http://k3d-registry.localhost:5000"]}}}')
```

Then we should see `k3d-mycluster` context:
```sh
kubectl config get-contexts
```
That context should be used from whatever Kubernetes interface (I recommend k9s).

# Create script

Let's create an "application" that we can package in Docker.
A simple script `myscript.sh`:
```sh
#!/bin/sh

echo Hello local Kubernetes!
```

# Package script in Docker

Then a `Dockerfile` so that we can package it:

```Dockerfile
FROM busybox

COPY myscript.sh myscript.sh
```

Build the image locally and push it to local registry.

```sh
docker build -t localhost:5000/myimage:latest .
docker push localhost:5000/myimage:latest
```

# Run script on Kubernetes

We will run a Kubernetes [Pod](https://kubernetes.io/docs/concepts/workloads/pods/).
We should create a spec for the Pod in `pod.yml`:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: mypod
spec:
  restartPolicy: Never
  containers:
    - name: mycontainer
      image: localhost:5000/myimage:latest
      command: ["/bin/sh", "myscript.sh"]
```

Then we can create this Pod:

```sh
kubectl apply -f pod.yml
```

It probably already run instantly, and we can see the logs:

```sh
kubectl logs pod/mypod
```

It should say `Hello local Kubernetes!`.

# Going further

Our application is probably going to be more complex.
E.g. we can use [Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/), set up a [Service](https://kubernetes.io/docs/concepts/services-networking/service/), and [port-forwarding](https://kubernetes.io/docs/tasks/access-application-cluster/port-forward-access-application-cluster/) so that we can look at our service in browser.
But this really depends on application.
