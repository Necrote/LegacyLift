{{/*
Release-scoped names, so two installs of this chart in one namespace do not collide.
*/}}
{{- define "inventory-service.name" -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "inventory-service.dbName" -}}
{{- printf "%s-db" (include "inventory-service.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
The Secret holding the datasource credentials: the one this chart creates, unless the operator
pointed existingSecret at their own.
*/}}
{{- define "inventory-service.secretName" -}}
{{- if .Values.existingSecret -}}
{{- .Values.existingSecret -}}
{{- else -}}
{{- include "inventory-service.dbName" . -}}
{{- end -}}
{{- end -}}

{{- define "inventory-service.labels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}
