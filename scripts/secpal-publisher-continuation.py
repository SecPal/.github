#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Restore authenticated publisher evidence and call the central risk observer."""

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from importlib import util

spec = util.spec_from_file_location("reevaluation", Path(__file__).with_name("secpal-vulnerability-reevaluation.py"))
reevaluation = util.module_from_spec(spec)
spec.loader.exec_module(reevaluation)
ARCHES = ("amd64", "arm64")
WORKFLOW = ".github/workflows/publish-container.yml"
OWNERS = {"SecPal/api": 3061, "SecPal/frontend": 2322}


def digest(path):
    with path.open("rb") as source:
        return "sha256:" + hashlib.file_digest(source, "sha256").hexdigest()


def gh_get(endpoint):
    return json.loads(subprocess.check_output(["gh", "api", endpoint], timeout=45, stderr=subprocess.DEVNULL))


def check_writer():
    repository = os.environ["GITHUB_REPOSITORY"]
    commit = os.environ["GITHUB_SHA"]
    if (repository not in OWNERS or not re.fullmatch(r"[a-f0-9]{40}", commit)
            or os.environ.get("GITHUB_REF") != "refs/heads/main"
            or os.environ.get("GITHUB_REF_PROTECTED") != "true"
            or os.environ.get("GITHUB_WORKFLOW_REF") != f"{repository}/{WORKFLOW}@refs/heads/main"
            or os.environ.get("GITHUB_WORKFLOW_SHA") != commit
            or os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch"):
        raise reevaluation.ContractError("PUBLISHER_WRITER_CONTEXT")
    return repository, commit


def verify_frontend_writer(repository, commit):
    run, attempt = (os.environ.get(key, "") for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"))
    if (os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"
            or not re.fullmatch(r"[1-9][0-9]{0,17}", run)
            or not re.fullmatch(r"[1-9][0-9]{0,5}", attempt)):
        raise reevaluation.ContractError("PUBLISHER_WRITER_INVOCATION")
    prefix = f"repos/{repository}"
    workflow = gh_get(f"{prefix}/actions/workflows/publish-container.yml")
    writer = gh_get(f"{prefix}/actions/runs/{run}/attempts/{attempt}")
    origin, head = writer["repository"], writer["head_repository"]
    if (workflow["path"] != WORKFLOW or writer["workflow_id"] != workflow["id"]
            or writer["path"] not in (WORKFLOW, WORKFLOW + "@main")
            or origin["full_name"] != repository or head["full_name"] != repository
            or origin["id"] != head["id"] or writer["head_sha"] != commit
            or writer["head_branch"] != "main" or writer["event"] != "workflow_dispatch"
            or writer["status"] != "in_progress" or writer["id"] != int(run)
            or writer["run_attempt"] != int(attempt)):
        raise reevaluation.ContractError("PUBLISHER_WRITER_INVOCATION")


def extract(archive, destination):
    with zipfile.ZipFile(archive) as packed:
        files = packed.infolist()
        if (len(files) > 1024 or sum(item.file_size for item in files) > 2 * 1024**3
                or len({item.filename for item in files}) != len(files)):
            raise reevaluation.ContractError("PUBLISHER_ARTIFACT_ZIP_BOUNDS")
        for item in files:
            name = Path(item.filename)
            if name.is_absolute() or ".." in name.parts or "\\" in item.filename or stat.S_ISLNK(item.external_attr >> 16):
                raise reevaluation.ContractError("PUBLISHER_ARTIFACT_ZIP_PATH")
        destination.mkdir(parents=True)
        packed.extractall(destination)


def restore(root, run, attempt):
    repository, commit = check_writer()
    producer = commit
    slug = repository.split("/")[1]
    if str(run) == os.environ.get("GITHUB_RUN_ID"):
        raise reevaluation.ContractError("PUBLISHER_PRODUCER_MUST_PRECEDE_WRITER")
    suffix = f"{run}-{attempt}"
    native = {f"{slug}-native-{arch}-{suffix}" for arch in ARCHES}
    if slug == "api":
        candidate = f"api-candidate-{suffix}"
        jobs = {"Attest unpublished API deployment candidate", "Repository Security / Accept API Repository Security",
                *(f"Build native API candidates / Native API ({arch})" for arch in ARCHES)}
    else:
        verify_frontend_writer(repository, commit)
        producer = gh_get(f"repos/{repository}/actions/runs/{run}/attempts/{attempt}")["head_sha"]
        candidate = f"frontend-pre-registry-{suffix}"
        jobs = {"Qualify both exact unpublished OCI subjects", "Repository Security / Repository Security",
                *(f"Build native Frontend candidates / Native frontend ({arch})" for arch in ARCHES)}
    artifacts = reevaluation.observe_retained_publisher(repository, commit, run, attempt,
        native | {candidate}, jobs, get=gh_get, producer_source=producer)
    retained = root / "retained"
    with tempfile.TemporaryDirectory(prefix="publisher-archive-") as folder:
        archive = Path(folder) / "artifact.zip"
        for name, artifact in artifacts.items():
            try:
                with archive.open("wb") as destination:
                    subprocess.run(["gh", "api", f"repos/{repository}/actions/artifacts/{artifact['id']}/zip"],
                                   stdout=destination, stderr=subprocess.DEVNULL, check=True, timeout=240)
                if archive.stat().st_size != artifact["size_in_bytes"] or digest(archive) != artifact["digest"]:
                    raise reevaluation.ContractError("PUBLISHER_ARTIFACT_TRANSPORT_DIGEST")
                extract(archive, retained if name == candidate else root / "native" / name)
            except (OSError, zipfile.BadZipFile, subprocess.SubprocessError) as error:
                raise reevaluation.ContractError("PUBLISHER_ARTIFACT_RESTORE") from error

    if slug == "api":
        signed = [retained / "unpublished-runtime-pair.json", retained / "source-security.json"]
        signed.extend(retained / role / arch / "evaluation.json"
                      for role in ("php-fpm", "nginx") for arch in ARCHES)
        bundle = retained / "bundle.jsonl"
    else:
        signed = [retained / "publisher" / name for name in ("pre-registry.json", "source-security.json")]
        bundle = retained / "publisher/pre-registry.bundle.json"
    for path in signed:
        try:
            verified = json.loads(subprocess.check_output([
                "gh", "attestation", "verify", str(path), "--bundle", str(bundle), "--repo", repository,
                "--signer-workflow", f"{repository}/{WORKFLOW}", "--signer-digest", producer, "--source-ref",
                "refs/heads/main", "--source-digest", producer, "--deny-self-hosted-runners", "--format", "json",
            ], timeout=120, stderr=subprocess.DEVNULL))
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            raise reevaluation.ContractError("PUBLISHER_PRODUCER_ATTESTATION") from error
        reevaluation.verify_retained_publisher_attestation(verified, path, repository, run, attempt)
    reevaluation._write_json(retained / "producer.json", {
        "repository": repository, "source_commit": producer, "run_id": str(run), "run_attempt": str(attempt),
        "workflow": WORKFLOW,
        "artifacts": {name: {"id": artifact["id"], "digest": artifact["digest"]} for name, artifact in artifacts.items()},
    })


def bound_platform(folder, subject, config_digest, spdx_digest, material):
    """Reproduce the originally recorded result from retained native scanner bytes."""
    module, schemas, policy, catalog = material
    read = reevaluation._read_json
    recorded = read(folder / "evaluation.json")
    original = read(folder / "policy-result.json")
    spdx = (folder / "sbom/syft.spdx.json").read_bytes()
    association_path = folder / "sbom/association.json"
    association = reevaluation.verify_syft_association(read(association_path), spdx, subject)
    if association["spdx_digest"] != spdx_digest:
        raise reevaluation.ContractError("PUBLISHER_RETAINED_SPDX")
    adapted = [
        reevaluation.adapt_grype(read(folder / "raw/grype.json"), read(folder / "grype-metadata.json"),
                                read(folder / "grype-input.json"), spdx, association),
        reevaluation.adapt_trivy(read(folder / "raw/trivy.json"), read(folder / "trivy-metadata.json")),
    ]
    inventory = {key: association[key] for key in ("format", "spdx_digest", "subject")}
    calculated = reevaluation.assemble_evaluation(subject, inventory, adapted, recorded["evaluated_at"])
    if recorded != calculated:
        raise reevaluation.ContractError("PUBLISHER_RETAINED_NORMALIZATION")
    now = reevaluation.datetime.now(reevaluation.timezone.utc).isoformat()
    current = module.evaluate(dict(calculated, evaluated_at=now), policy, reviewed_vex=catalog, schemas=schemas)
    if (current["evidence_health"]["state"] != "HEALTHY"
            or dict(current, evaluated_at=recorded["evaluated_at"]) != original):
        raise reevaluation.ContractError("PUBLISHER_RETAINED_POLICY_CHANGED")
    raw = {scanner: digest(folder / "raw" / f"{scanner}.json") for scanner in ("grype", "trivy")}
    records = read(folder / "scan-records.json")
    if len(records) != 2 or {row["scanner"] for row in records} != set(raw):
        raise reevaluation.ContractError("PUBLISHER_RETAINED_SCANNERS")
    for record in records:
        run = next(run for run in original["scanner_runs"] if run["scanner"] == record["scanner"])
        binding = spdx_digest if record["scanner"] == "grype" else subject["oci_digest"]
        if ((record["platform"], record["subject_digest"], record["evidence_sha256"], record["completed_at"],
             record["database"], record["scanner_version"], record["status"], record["policy_result"])
                != (subject["platform"], binding, raw[record["scanner"]], run["completed_at"], run["database"],
                    run["scanner_identity"]["version"], "SUCCEEDED", original["gate_state"])):
            raise reevaluation.ContractError("PUBLISHER_RETAINED_SCAN_RECORD")
    return dict(evaluation=calculated, policy_result_sha256=module._document_digest(original),
                config_digest=config_digest, spdx_association_sha256=digest(association_path), raw=raw)


def snapshot(root, vex_root):
    repository, writer = check_writer()
    retained = root / "retained"
    read = reevaluation._read_json
    producer = read(retained / "producer.json")
    commit = producer["source_commit"]
    if (producer["repository"] != repository or not re.fullmatch(r"[a-f0-9]{40}", commit)
            or (repository == "SecPal/api" and commit != writer)):
        raise reevaluation.ContractError("PUBLISHER_RETAINED_SOURCE")
    material = reevaluation.risk_policy_material(vex_root)
    module, _, policy, _ = material
    api = repository == "SecPal/api"
    publisher = retained if api else retained / "publisher"
    security = publisher / "source-security.json"
    record = read(security)
    now = reevaluation.datetime.now(reevaluation.timezone.utc)
    stamp = module.parse_time
    if (record["subject"] != {"repository": repository, "commit": commit}
            or record["gate_state"] != "CLEAN" or record["findings"]
            or record["operation"] != {"name": "TRIVY_REPOSITORY_SCAN", "status": "SUCCEEDED"}
            or record["database"]["status"] != "FRESH"
            or not stamp(record["database"]["updated_at"])
            <= now < stamp(record["database"]["next_update"])):
        raise reevaluation.ContractError("PUBLISHER_RETAINED_SOURCE_SECURITY")
    evidence = {
        "source": {"repository": repository, "commit": commit},
        "evidence": {"policy_sha256": module._document_digest(policy), "producer": producer,
                     "source_security_sha256": digest(security)},
    }
    if api:
        claim_path = publisher / "unpublished-runtime-pair.json"
        claim = read(claim_path)
        if (claim["source"]["commit"] != commit or claim["source"]["repository"] != "https://github.com/" + repository
                or claim["published"] is not False or claim["qualification"] != "SUCCEEDED"
                or claim["workflow"] != {
                    "repository": repository, "path": ".github/workflows/container-image.yml",
                    "run_id": producer["run_id"], "run_attempt": producer["run_attempt"],
                }
                or claim["pair_sha256"] != reevaluation.sha256_digest(
                    reevaluation._canonical({"source": claim["source"], "images": claim["images"]}).encode())
                or set(claim["images"]) != {"php-fpm", "nginx"}):
            raise reevaluation.ContractError("PUBLISHER_RETAINED_PAIR")
        evidence.update(pair_receipt_sha256=digest(claim_path), components={}, native_pair_smoke={})
        for role in ("php-fpm", "nginx"):
            image = claim["images"][role]
            rows = []
            for arch, row in zip(ARCHES, image["platforms"], strict=True):
                platform = "linux/" + arch
                subject = {"platform": platform, "oci_digest": row["subject"]["manifest_digest"]}
                smoke = row["smoke"]
                native = root / "native" / f"api-native-{arch}-{producer['run_id']}-{producer['run_attempt']}" / role
                scan = retained / role / arch
                recorded = read(scan / "policy-result.json")
                if (row["subject"]["platform"] != platform or smoke != read(native / "smoke.json")
                        or smoke["digest"] != subject["oci_digest"]
                        or smoke["workflow_run_id"] != producer["run_id"] or smoke["workflow_run_attempt"] != producer["run_attempt"]
                        or smoke["test"] != "tests/docker/smoke.sh"
                        or row["scans"] != read(scan / "scan-records.json")
                        or row["policy_sha256"] != reevaluation.sha256_digest(reevaluation._canonical(
                            dict(recorded, evaluated_at=claim["generated_at"])).encode())):
                    raise reevaluation.ContractError("PUBLISHER_RETAINED_PAIR_PLATFORM")
                entries = evidence["native_pair_smoke"]
                if platform in entries and entries[platform]["runtime_pair"] != smoke["runtime_pair"]:
                    raise reevaluation.ContractError("PUBLISHER_RETAINED_PAIR_SMOKE")
                entries[platform] = smoke
                rows.append(bound_platform(scan, subject, row["subject"]["config_digest"], row["sbom_sha256"], material))
            evidence["components"][role] = {"index_digest": image["candidate_index_digest"], "platforms": rows}
    else:
        prepared = publisher / "prepared.json"
        claim_path = publisher / "pre-registry.json"
        claim = read(claim_path)
        source = read(prepared)
        if (claim["candidate_sha256"] != digest(prepared) or digest(publisher / "index.json") != source["index_digest"]
                or len(claim["results"]) != 2):
            raise reevaluation.ContractError("PUBLISHER_RETAINED_FRONTEND_RECEIPT")
        evidence["evidence"]["qualification_receipt_sha256"] = digest(claim_path)
        rows = []
        for arch, native, inventory, binding in zip(ARCHES, source["records"], source["inventories"], claim["results"], strict=True):
            platform = "linux/" + arch
            subject = {"platform": platform, "oci_digest": native["subject"]["manifest_digest"]}
            scan = retained / "scan" / arch
            if (native["source"]["commit"] != commit or native["source"]["repository"] != "https://github.com/" + repository
                    or native["workflow_run_id"] != producer["run_id"] or native["workflow_run_attempt"] != producer["run_attempt"]
                    or native["subject"]["platform"] != platform or inventory["platform"] != platform
                    or binding != dict(subject=subject, evaluation_sha256=digest(scan / "evaluation.json"),
                                       policy_sha256=digest(scan / "policy-result.json"))):
                raise reevaluation.ContractError("PUBLISHER_RETAINED_FRONTEND_PLATFORM")
            rows.append(bound_platform(scan, subject, native["subject"]["config_digest"], inventory["spdx_sha256"], material))
        evidence.update(index_digest=source["index_digest"], platforms=rows)
    module._risk_subject(evidence)
    return evidence


def observe(evidence, vex_root):
    repository, commit = check_writer()
    source = evidence["source"]
    if source["repository"] != repository or (repository == "SecPal/api" and source["commit"] != commit):
        raise reevaluation.ContractError("PUBLISHER_ADMISSION_SOURCE")
    if repository == "SecPal/frontend":
        producer = evidence["evidence"]["producer"]
        if (producer["repository"] != repository or producer["source_commit"] != source["commit"]
                or producer["workflow"] != WORKFLOW or producer["run_id"] == os.environ.get("GITHUB_RUN_ID")):
            raise reevaluation.ContractError("PUBLISHER_ADMISSION_SOURCE")
        verify_frontend_writer(repository, commit)
        if source["commit"] != commit:
            reevaluation.verify_frontend_producer_source(source["commit"], commit, get=gh_get)
    # Read the accepted source independently of the retained producer.
    branch = gh_get(f"repos/{repository}/branches/main")
    if (branch["protected"] is not True or branch["commit"]["sha"] != commit
            or branch["commit"]["commit"]["verification"]["verified"] is not True):
        raise reevaluation.ContractError("PUBLISHER_WRITER_SOURCE")
    catalog_commit = reevaluation._git(vex_root, "rev-parse", "HEAD").strip()
    catalog = gh_get("repos/SecPal/.github/branches/main")
    if catalog["protected"] is not True or catalog["commit"]["sha"] != catalog_commit:
        raise reevaluation.ContractError("PUBLISHER_VEX_CHECKOUT")
    locator = os.environ.get("ARTIFACT_RISK_ACCEPTANCE_COMMENT_ID", "")
    if not re.fullmatch(r"[1-9][0-9]{0,18}", locator):
        raise reevaluation.ContractError("PUBLISHER_RISK_LOCATOR")
    return reevaluation.observe_artifact_risk_acceptance(evidence, int(locator),
        issue_number=OWNERS[repository], get=gh_get, vex_root=vex_root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    original = commands.add_parser("restore")
    original.add_argument("--root", type=Path, required=True)
    original.add_argument("--run", type=int, required=True)
    original.add_argument("--attempt", type=int, required=True)
    staging = commands.add_parser("snapshot")
    staging.add_argument("--root", type=Path, required=True)
    staging.add_argument("--vex-root", type=Path, required=True)
    staging.add_argument("--output", type=Path, required=True)
    decision = commands.add_parser("observe")
    decision.add_argument("--evidence", type=Path, required=True)
    decision.add_argument("--vex-root", type=Path, required=True)
    decision.add_argument("--output", type=Path, required=True)
    decision.add_argument("--compare", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "restore":
            restore(args.root, args.run, args.attempt)
        elif args.command == "snapshot":
            evidence = snapshot(args.root, args.vex_root)
            reevaluation._write_json(args.output, evidence)
            module, _, _, _ = reevaluation.risk_policy_material(args.vex_root)
            print(module._document_digest(evidence))
        else:
            receipt = observe(reevaluation._read_json(args.evidence), args.vex_root)
            if args.compare:
                previous = reevaluation._read_json(args.compare)
                if any(receipt[key] != previous[key] for key in ("comment", "operator", "evidence_sha256", "decision")):
                    raise reevaluation.ContractError("PUBLISHER_DECISION_CHANGED")
            reevaluation._write_json(args.output, receipt)
    except reevaluation.ContractError as error:
        print("FAIL: " + str(error), file=sys.stderr)
        return 1
    except (OSError, KeyError, TypeError, ValueError, subprocess.SubprocessError):
        print("FAIL: PUBLISHER_CONTINUATION_INPUT", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
