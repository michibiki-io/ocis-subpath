{{- define "ocis-subpath.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "ocis-subpath.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := include "ocis-subpath.name" . -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "ocis-subpath.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "ocis-subpath.labels" -}}
helm.sh/chart: {{ include "ocis-subpath.chart" . }}
app.kubernetes.io/name: {{ include "ocis-subpath.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "ocis-subpath.selectorLabels" -}}
app.kubernetes.io/name: {{ include "ocis-subpath.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "ocis-subpath.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "ocis-subpath.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{- define "ocis-subpath.normalizedSubpath" -}}
{{- $subpath := default "/" .Values.ocis.subpath -}}
{{- $trimmed := regexReplaceAll "/+$" $subpath "" -}}
{{- if or (eq $subpath "") (eq $subpath "/") (eq $trimmed "") -}}
/
{{- else if hasPrefix "/" $trimmed -}}
{{- $trimmed -}}
{{- else -}}
/{{ $trimmed }}
{{- end -}}
{{- end -}}

{{- define "ocis-subpath.publicUrl" -}}
{{- $override := .Values.ocis.publicUrlOverride | trim -}}
{{- if $override -}}
{{- regexReplaceAll "/+$" $override "" -}}
{{- else -}}
{{- $base := regexReplaceAll "/+$" .Values.ocis.baseUrl "" -}}
{{- $subpath := include "ocis-subpath.normalizedSubpath" . | trim -}}
{{- if eq $subpath "/" -}}
{{- $base -}}
{{- else -}}
{{- printf "%s%s" $base $subpath -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "ocis-subpath.oidcAuthority" -}}
{{- $authority := .Values.ocis.oidc.authority | trim -}}
{{- if $authority -}}
{{- regexReplaceAll "/+$" $authority "" -}}
{{- else if .Values.ocis.oidc.issuer | trim -}}
{{- regexReplaceAll "/+$" (.Values.ocis.oidc.issuer | trim) "" -}}
{{- else -}}
{{- include "ocis-subpath.publicUrl" . -}}
{{- end -}}
{{- end -}}

{{- define "ocis-subpath.oidcMetadataUrl" -}}
{{- $metadata := .Values.ocis.oidc.metadataUrl | trim -}}
{{- if $metadata -}}
{{- regexReplaceAll "/+$" $metadata "" -}}
{{- else if .Values.ocis.oidc.external.enabled -}}
{{- printf "%s/.well-known/openid-configuration" (include "ocis-subpath.oidcAuthority" .) -}}
{{- else -}}
{{- printf "%s/.well-known/openid-configuration" (include "ocis-subpath.publicUrl" .) -}}
{{- end -}}
{{- end -}}

{{- define "ocis-subpath.probePath" -}}
{{- $subpath := include "ocis-subpath.normalizedSubpath" . | trim -}}
{{- if eq $subpath "/" -}}
/healthz
{{- else -}}
{{- printf "%s/healthz" $subpath -}}
{{- end -}}
{{- end -}}

{{- define "ocis-subpath.secretName" -}}
{{- if .Values.ocis.existingSecret -}}
{{- .Values.ocis.existingSecret -}}
{{- else if .Values.ocis.generatedSecrets.enabled -}}
{{- include "ocis-subpath.fullname" . -}}
{{- else -}}
{{- "" -}}
{{- end -}}
{{- end -}}
