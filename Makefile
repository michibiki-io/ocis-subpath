PYTHON ?= python3

.PHONY: build-patcher helm-lint helm-template helm-template-role-assignment compose-up compose-down compose-reset e2e e2e-shell e2e-runner e2e-helm-kind clean

build-patcher:
	./scripts/build-patcher-image.sh

helm-lint:
	helm lint charts/ocis-subpath

helm-template:
	helm template ocis charts/ocis-subpath

helm-template-role-assignment:
	./scripts/helm-template-role-assignment.sh

compose-up:
	./scripts/compose/up.sh

compose-down:
	./scripts/compose/down.sh

compose-reset:
	./scripts/compose/down.sh --volumes

e2e: e2e-helm-kind

e2e-shell:
	./scripts/e2e/shell.sh

e2e-helm-kind:
	./scripts/e2e/helm-kind.sh

e2e-runner:
	./scripts/e2e/shell.sh -lc ./scripts/e2e/run.sh

clean:
	rm -rf compose/.generated tests/e2e/node_modules tests/e2e/.npm-cache tests/e2e/playwright-report tests/e2e/test-results
