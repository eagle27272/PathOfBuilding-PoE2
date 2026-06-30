#!/bin/sh
set -eu

case "$0" in
	/*) SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P) ;;
	*) SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$PWD/$0")" && pwd -P) ;;
esac
REPO_DIR=${POB_RUNTIME_REPO_DIR:-$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd -P)}
ASSET_DIR=${1:-${POB_RUNTIME_ASSET_DIR:-}}
SIMPLEGRAPHIC_RUNTIME_INDEX=${SIMPLEGRAPHIC_RUNTIME_INDEX:-SimpleGraphicRuntime-index.json}
POB_RUNTIME_INDEX=${POB_RUNTIME_INDEX:-PathOfBuildingRuntime-index.json}

if [ -z "$ASSET_DIR" ] || [ ! -d "$ASSET_DIR" ]; then
	printf 'Usage: %s <asset-directory>\n' "$0" >&2
	exit 2
fi

case "$ASSET_DIR" in
	/*) ASSET_DIR_ABS=$ASSET_DIR ;;
	*) ASSET_DIR_ABS=$(CDPATH= cd -- "$ASSET_DIR" && pwd -P) ;;
esac

python3 "$SCRIPT_DIR/verify-runtime-index.py" \
	"$ASSET_DIR_ABS" \
	"$ASSET_DIR_ABS/$SIMPLEGRAPHIC_RUNTIME_INDEX"
has_pob_runtime=0
for asset in "$ASSET_DIR_ABS"/PathOfBuildingRuntime-*.tar "$ASSET_DIR_ABS"/PathOfBuildingRuntime-*.tar.gz "$ASSET_DIR_ABS"/PathOfBuildingRuntime-*.tgz; do
	if [ -f "$asset" ]; then
		has_pob_runtime=1
		break
	fi
done
if [ "$has_pob_runtime" -eq 1 ]; then
	if [ ! -f "$ASSET_DIR_ABS/$POB_RUNTIME_INDEX" ]; then
		printf 'PathOfBuilding runtime archives require %s in %s\n' "$POB_RUNTIME_INDEX" "$ASSET_DIR_ABS" >&2
		exit 1
	fi
	python3 "$SCRIPT_DIR/verify-pob-runtime-index.py" \
		"$ASSET_DIR_ABS" \
		"$ASSET_DIR_ABS/$POB_RUNTIME_INDEX"
fi
POB_RUNTIME_REPO_DIR=$REPO_DIR "$SCRIPT_DIR/install-runtime-assets.sh" "$ASSET_DIR_ABS"
(cd "$REPO_DIR" && python3 update_manifest.py --quiet --in-place)
