#!/usr/bin/env bash
#
# Shared constants + helpers for PortPax pull scripts (LOCAL ← DEV / PROD).
# Source from other scripts — do not execute directly.
#
# Pull matrix (automated):
#   sync_db_from_dev.sh      DEV Postgres  → LOCAL (SSH)
#   sync_db_from_prod.sh     PROD RDS      → LOCAL (SSM + S3); --target=dev → DEV
#   sync_media_from_dev.sh   DEV media/    → LOCAL (rsync SSH)
#   sync_media_from_prod.sh  PROD S3 files → LOCAL (aws s3 sync)
#
# Push (media / files.json / DB → DEV|PROD): NOT automated — use AWS CLI / SSH manually.
#
# IAM (PROD pull) — laptop/SSO profile needs roughly:
#   ssm:SendCommand, ssm:ListCommandInvocations, ssm:GetCommandInvocation
#     on instance i-0bf7f41727c6d932e
#   s3:GetObject (+ ListBucket) on s3://…-releases-…/ops/db/*
#   s3:GetObject (+ ListBucket) on the files bucket (media sync)
# EC2 instance role needs s3:PutObject on ops/db/* (upload dump after backup).
#
# Env overrides:
#   AWS_PROFILE / AWS_REGION
#   PORTPAX_PROD_INSTANCE_ID
#   PORTPAX_RELEASES_BUCKET
#   PORTPAX_FILES_BUCKET
#   PORTPAX_DEV_HOST / PORTPAX_DEV_PATH
#

# Guard: source only
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  echo "ERROR: source this file from another script (do not execute)." >&2
  exit 1
fi

# --- DEV (SSH) ---
PORTPAX_DEV_HOST="${PORTPAX_DEV_HOST:-portpax-api}"
PORTPAX_DEV_PATH="${PORTPAX_DEV_PATH:-/home/git/backend}"

# --- PROD (SSM + S3) ---
PORTPAX_PROD_INSTANCE_ID="${PORTPAX_PROD_INSTANCE_ID:-i-0bf7f41727c6d932e}"
PORTPAX_RELEASES_BUCKET="${PORTPAX_RELEASES_BUCKET:-itm-portpax-prod-releases-040105284691}"
PORTPAX_FILES_BUCKET="${PORTPAX_FILES_BUCKET:-itm-portpax-prod-files-040105284691}"
PORTPAX_AWS_REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
PORTPAX_OPS_DB_PREFIX="${PORTPAX_OPS_DB_PREFIX:-ops/db}"

portpax_require_cmd() {
  local c
  for c in "$@"; do
    if ! command -v "$c" >/dev/null 2>&1; then
      echo "ERROR: required command not found: $c" >&2
      return 1
    fi
  done
}

portpax_require_aws() {
  if ! portpax_require_cmd aws python3; then
    echo "HINT: brew install awscli   # then: aws sso login --profile portpax-prod" >&2
    return 1
  fi
  if ! aws sts get-caller-identity --region "$PORTPAX_AWS_REGION" >/dev/null 2>&1; then
    echo "ERROR: AWS CLI not authenticated for this profile/session." >&2
    echo "HINT: export AWS_PROFILE=portpax-prod && aws sso login --profile portpax-prod" >&2
    echo "      (or aws configure list-profiles  to see available names)" >&2
    return 1
  fi
}

portpax_require_ssh() {
  portpax_require_cmd ssh scp
}

# Run a bash body on PROD API via SSM SendCommand; stream remote stdout/stderr.
# Args: comment, remote_body (runs under bash -lc on the instance)
# Prints remote StandardOutputContent to stdout; returns non-zero on failure.
portpax_ssm_run() {
  local comment="$1"
  local remote_body="$2"
  local params command_id status output err_output i

  portpax_require_aws || return 1

  params="$(
    PORTPAX_SSM_BODY="$remote_body" python3 - <<'PY'
import json, os, shlex
body = os.environ["PORTPAX_SSM_BODY"]
cmd = "bash -lc " + shlex.quote(body)
print(json.dumps({"commands": [cmd]}))
PY
  )"

  command_id="$(
    aws ssm send-command \
      --region "$PORTPAX_AWS_REGION" \
      --instance-ids "$PORTPAX_PROD_INSTANCE_ID" \
      --document-name "AWS-RunShellScript" \
      --comment "$comment" \
      --parameters "$params" \
      --query "Command.CommandId" \
      --output text
  )"

  echo "[portpax_ssm] CommandId=${command_id} (${comment})" >&2

  for i in $(seq 1 120); do
    status="$(
      aws ssm list-command-invocations \
        --region "$PORTPAX_AWS_REGION" \
        --command-id "$command_id" \
        --details \
        --query "CommandInvocations[0].Status" \
        --output text 2>/dev/null || echo "Pending"
    )"
    case "$status" in
      Success)
        aws ssm list-command-invocations \
          --region "$PORTPAX_AWS_REGION" \
          --command-id "$command_id" \
          --details \
          --query "CommandInvocations[0].CommandPlugins[0].Output" \
          --output text
        return 0
        ;;
      Failed|Cancelled|TimedOut)
        output="$(
          aws ssm list-command-invocations \
            --region "$PORTPAX_AWS_REGION" \
            --command-id "$command_id" \
            --details \
            --query "CommandInvocations[0].CommandPlugins[0].Output" \
            --output text 2>/dev/null || true
        )"
        err_output="$(
          aws ssm get-command-invocation \
            --region "$PORTPAX_AWS_REGION" \
            --command-id "$command_id" \
            --instance-id "$PORTPAX_PROD_INSTANCE_ID" \
            --query "StandardErrorContent" \
            --output text 2>/dev/null || true
        )"
        echo "$output" >&2
        [[ -n "$err_output" && "$err_output" != "None" ]] && echo "$err_output" >&2
        echo "ERROR: SSM command ${status} (CommandId=${command_id})" >&2
        return 1
        ;;
    esac
    sleep 5
  done

  echo "ERROR: timed out waiting for SSM command ${command_id}" >&2
  return 1
}

portpax_s3_cp_down() {
  local s3_uri="$1"
  local dest="$2"
  portpax_require_aws || return 1
  aws s3 cp "$s3_uri" "$dest" --region "$PORTPAX_AWS_REGION"
}

portpax_s3_sync_down() {
  local s3_uri="$1"
  local dest="$2"
  shift 2
  portpax_require_aws || return 1
  aws s3 sync "$s3_uri" "$dest" --region "$PORTPAX_AWS_REGION" "$@"
}
