# oCIS Subpath project / oCIS Subpath プロジェクト

## Table of Contents / 目次

- [English](#english)
  - [Overview](#overview)
  - [Run the compose stack](#run-the-compose-stack)
  - [Render or install the Helm chart](#render-or-install-the-helm-chart)
  - [Validation and E2E](#validation-and-e2e)
  - [Release](#release)
- [日本語](#日本語)
  - [概要](#概要)
  - [compose スタックの起動](#compose-スタックの起動)
  - [Helm chart のレンダリングまたはインストール](#helm-chart-のレンダリングまたはインストール)
  - [検証と E2E](#検証と-e2e)
  - [リリース](#リリース)

## English

### Overview

This repository provides a subpath adapter for serving ownCloud Infinite Scale and ownCloud Web at URLs such as `https://example.com/ocis/`.

### Run the compose stack

```bash
cp compose/.env.example compose/.env
./scripts/compose/up.sh
```

The local stack is exposed at `https://ocis.local:9200/ocis`.

### Render or install the Helm chart

```bash
helm lint charts/ocis-subpath
helm template ocis charts/ocis-subpath \
  --set ocis.baseUrl=https://example.com \
  --set ocis.subpath=/ocis \
  --set ocis.existingSecret=ocis-secrets
```

Chart-specific details are documented in [charts/ocis-subpath/README.md](charts/ocis-subpath/README.md).

### Validation and E2E

The canonical E2E flow runs the Helm chart on kind. Validation flows, Playwright usage, troubleshooting, and implementation notes are documented in [docs/e2e.md](docs/e2e.md).

### Release

Release streams are split by artifact:

- patched oCIS backend image: `ocis/v8.0.4-subpath.1`
- ownCloud Web assets patcher image: `patcher/web-v12.4.0-subpath.3`
- Helm chart: `chart/v0.2.5`

The upstream tracking workflow opens an issue and a draft PR when `owncloud/ocis` or `owncloud/web` moves. Generated PRs get `release-on-merge` by default; closing the PR discards the proposed version changes, while merging it publishes the release artifacts. Release details are documented in [docs/release.md](docs/release.md).

## 日本語

### 概要

このリポジトリは、ownCloud Infinite Scale と ownCloud Web を `https://example.com/ocis/` のような URL で提供するための subpath adapter を提供します。

### compose スタックの起動

```bash
cp compose/.env.example compose/.env
./scripts/compose/up.sh
```

ローカルスタックは `https://ocis.local:9200/ocis` で公開されます。

### Helm chart のレンダリングまたはインストール

```bash
helm lint charts/ocis-subpath
helm template ocis charts/ocis-subpath \
  --set ocis.baseUrl=https://example.com \
  --set ocis.subpath=/ocis \
  --set ocis.existingSecret=ocis-secrets
```

Chart 固有の詳細は [charts/ocis-subpath/README.md](charts/ocis-subpath/README.md) に記載しています。

### 検証と E2E

標準の E2E フローは kind 上で Helm chart を実行します。検証フロー、Playwright の使い方、トラブルシューティング、実装メモは [docs/e2e.md](docs/e2e.md) に記載しています。

### リリース

リリース系列は artifact ごとに分かれています。

- patched oCIS backend image: `ocis/v8.0.4-subpath.1`
- ownCloud Web assets patcher image: `patcher/web-v12.4.0-subpath.3`
- Helm chart: `chart/v0.2.5`

Upstream tracking workflow は `owncloud/ocis` または `owncloud/web` が更新されたときに issue と draft PR を作成します。生成された PR にはデフォルトで `release-on-merge` が付与されます。PR を close すると提案された version 変更は破棄され、merge すると release artifacts が公開されます。リリースの詳細は [docs/release.md](docs/release.md) に記載しています。
