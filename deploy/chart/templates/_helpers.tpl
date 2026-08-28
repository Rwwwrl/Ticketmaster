{{- define "ticketmaster.migrationJob" -}}
{{- $phase := .alembicTarget | splitList "@" | first -}}
apiVersion: batch/v1
kind: Job
metadata:
  name: {{ .service }}-migrate-{{ $phase }}
  labels:
    app: {{ .service }}-migrate-{{ $phase }}
  annotations:
    argocd.argoproj.io/sync-wave: {{ .syncWave | quote }}
    argocd.argoproj.io/sync-options: Force=true,Replace=true
spec:
  backoffLimit: 0
  activeDeadlineSeconds: 600
  template:
    metadata:
      labels:
        app: {{ .service }}-migrate-{{ $phase }}
    spec:
      restartPolicy: Never
      containers:
        - name: migrate
          image: '{{ .imageRepository }}:{{ .commitSha }}'
          command: ["poetry", "run", "alembic", "upgrade", "{{ .alembicTarget }}"]
          envFrom:
            - secretRef:
                name: {{ .externalSecretName }}
          resources:
            requests:
              cpu: 50m
              memory: 128Mi
            limits:
              cpu: 200m
              memory: 256Mi
{{- end -}}
