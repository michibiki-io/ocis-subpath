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

{{- define "ocis-subpath.urlOrigin" -}}
{{- $url := . | default "" | trim -}}
{{- if regexMatch "^https?://[^/?#]+([/?#].*)?$" $url -}}
{{- regexReplaceAll "^(https?://[^/?#]+).*$" $url "${1}" -}}
{{- end -}}
{{- end -}}

{{- define "ocis-subpath.cspDirectives" -}}
{{- $csp := .Values.ocis.csp | default dict -}}
{{- $directives := deepCopy ($csp.directives | default dict) -}}
{{- if .Values.ocis.oidc.external.enabled -}}
{{- $connectSrc := get $directives "connect-src" | default list -}}
{{- range $url := list .Values.ocis.oidc.issuer .Values.ocis.oidc.authority .Values.ocis.oidc.metadataUrl }}
{{- $origin := include "ocis-subpath.urlOrigin" $url | trim -}}
{{- if $origin -}}
{{- $connectSrc = append $connectSrc $origin -}}
{{- end -}}
{{- end -}}
{{- $_ := set $directives "connect-src" (uniq $connectSrc) -}}
{{- end -}}
{{- toYaml $directives -}}
{{- end -}}

{{- define "ocis-subpath.roleAssignmentMappingCount" -}}
{{- $mapping := . | default dict -}}
{{- $count := 0 -}}
{{- range $role := list "admin" "spaceadmin" "user" "guest" -}}
{{- $count = add $count (len (get $mapping $role | default list)) -}}
{{- end -}}
{{- $count -}}
{{- end -}}

{{- define "ocis-subpath.roleAssignmentMode" -}}
{{- $ra := .Values.ocis.roleAssignment | default dict -}}
{{- $mode := default "auto" $ra.mode -}}
{{- if eq $mode "auto" -}}
{{- $groupCount := include "ocis-subpath.roleAssignmentMappingCount" ($ra.groupMapping | default dict) | int -}}
{{- $userCount := include "ocis-subpath.roleAssignmentMappingCount" ($ra.userMapping | default dict) | int -}}
{{- if gt $groupCount 0 -}}
group
{{- else if gt $userCount 0 -}}
user
{{- else -}}
{{- fail "ocis.roleAssignment.enabled=true requires at least one groupMapping or userMapping entry" -}}
{{- end -}}
{{- else -}}
{{- $mode -}}
{{- end -}}
{{- end -}}

{{- define "ocis-subpath.roleAssignmentClaim" -}}
{{- $ra := .Values.ocis.roleAssignment | default dict -}}
{{- $mode := include "ocis-subpath.roleAssignmentMode" . | trim -}}
{{- if eq $mode "group" -}}
{{- required "ocis.roleAssignment.groupClaim is required when roleAssignment mode is group" ($ra.groupClaim | default "" | trim) -}}
{{- else if eq $mode "user" -}}
{{- required "ocis.roleAssignment.userClaim is required when roleAssignment mode is user" ($ra.userClaim | default "" | trim) -}}
{{- else -}}
{{- fail (printf "unsupported ocis.roleAssignment.mode %q" $mode) -}}
{{- end -}}
{{- end -}}

{{- define "ocis-subpath.roleAssignmentMapping" -}}
{{- $ra := .Values.ocis.roleAssignment | default dict -}}
{{- $mode := include "ocis-subpath.roleAssignmentMode" . | trim -}}
{{- $mapping := dict -}}
{{- if eq $mode "group" -}}
{{- $mapping = $ra.groupMapping | default dict -}}
{{- else if eq $mode "user" -}}
{{- $mapping = $ra.userMapping | default dict -}}
{{- else -}}
{{- fail (printf "unsupported ocis.roleAssignment.mode %q" $mode) -}}
{{- end -}}
{{- if eq (include "ocis-subpath.roleAssignmentMappingCount" $mapping | int) 0 -}}
{{- fail (printf "ocis.roleAssignment.%sMapping must contain at least one mapping entry" $mode) -}}
{{- end -}}
{{- range $role := list "admin" "spaceadmin" "user" "guest" -}}
{{- range $claimValue := get $mapping $role | default list }}
- role_name: {{ $role }}
  claim_value: {{ $claimValue | quote }}
{{- end -}}
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
