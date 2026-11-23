# SPDX-FileCopyrightText: 2026 SecPal Contributors
# SPDX-License-Identifier: MIT
"""Report official upstream runtime opportunities."""
import argparse
from datetime import date, datetime
from hashlib import sha256
import json
from pathlib import Path
import re
from urllib.request import urlopen

PHP_SUPPORT = "https://www.php.net/supported-versions.php"
PHP_RELEASE = "https://www.php.net/releases/index.php?json&max=1&version="
NGINX_DOWNLOADS = "https://nginx.org/en/download.html"
NGINX_ADVISORIES = "https://nginx.org/en/security_advisories.html"
IMAGES = "https://raw.githubusercontent.com/docker-library/official-images/master/library/"
VERSION = r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
SHA = r"[a-f0-9]{64}"
MARKER = "secpal-runtime-upgrade:"
IMAGE_SOURCE = {
    "php": "https://github.com/docker-library/php/tree/",
    "nginx": "https://github.com/nginx/docker-nginx/tree/",
}
NATIVE = {"amd64", "arm64v8"}


def read(url):
    with urlopen(url, timeout=20) as response:
        if response.url != url:
            raise ValueError(f"Unexpected redirect from {url}")
        payload = response.read(512_001)
    if len(payload) > 512_000:
        raise ValueError(f"Oversized upstream document at {url}")
    return payload.decode("utf-8")


def version_tuple(version):
    return tuple(map(int, version.split(".")))


def line(version):
    return version_tuple(version)[:2]


def baseline(containerfile):
    pins = {}
    for runtime, version, variant in re.findall(
        rf"^FROM docker\.io/library/(php|nginx):({VERSION})(-[a-z0-9.-]+)@sha256:{SHA} AS \w+(?:-\w+)*$",
        containerfile.read_text(), flags=re.M,
    ):
        if runtime in pins:
            raise ValueError(f"Duplicate approved {runtime} reference")
        pins[runtime] = (version, variant)
    if pins.keys() != IMAGE_SOURCE.keys():
        raise ValueError("Both approved runtime pins are required")
    return pins


def php_support(page, today):
    table = re.search(r"<h3>Currently Supported Versions</h3>\s*(<table\b.*?</table>)", page, re.S)
    if not table:
        raise ValueError("PHP support table is missing")
    supported = {}
    for row in re.findall(r'<tr class="(?:stable|security)">(.*?)</tr>', table[1], re.S):
        name = re.findall(r'<a href="/downloads\.php\?version=(\d+\.\d+)">\1</a>', row)
        dates = re.findall(r"<td>(\d{1,2} [A-Z][a-z]{2} \d{4})</td>", row)
        if len(name) != 1 or len(dates) != 3 or name[0] in supported:
            raise ValueError("Invalid PHP support row")
        if today <= datetime.strptime(dates[2], "%d %b %Y").date():
            supported[name[0]] = dates[1:]
    if not supported:
        raise ValueError("PHP support list is missing")
    return supported


def php_release(releases, branch):
    versions = json.loads(releases)
    if not isinstance(versions, dict) or len(versions) != 1:
        raise ValueError(f"Expected one official PHP release for {branch}")
    version, release = next(iter(versions.items()))
    if (not isinstance(release, dict) or release.get("version", version) != version or
            not re.fullmatch(VERSION, version) or line(version) != line(branch)):
        raise ValueError(f"Unexpected PHP release for {branch}")
    archives = [entry.get("sha256", "") for entry in release["source"]
                if entry.get("filename") == f"php-{version}.tar.gz"]
    if len(archives) != 1 or not re.fullmatch(SHA, archives[0]):
        raise ValueError(f"Missing official PHP {version} archive checksum")
    return version, archives[0], "security" in release.get("tags", [])


def nginx_releases(page):
    releases = {}
    for channel, table in re.findall(
        r"<h4>(Mainline|Stable) version</h4>\s*(?:</center>\s*)?(<table\b.*?</table>)", page, re.S
    ):
        archives = re.findall(rf'href="/download/nginx-({VERSION})\.tar\.gz"', table)
        if (len(archives) != 1 or channel in releases or
                f'href="/download/nginx-{archives[0]}.tar.gz.asc"' not in table):
            raise ValueError(f"Invalid Nginx {channel} release")
        releases[channel] = archives[0]
    if releases.keys() != {"Mainline", "Stable"}:
        raise ValueError("Both official Nginx channels are required")
    return releases


def nginx_fix_comparison(advisories, approved, candidate):
    shared = set()
    candidate_only = set()
    for advisory in re.findall(r"<li><p>(.*?)</p></li>", advisories, re.S):
        ids = set(re.findall(r"CVE-\d{4}-\d{4,}", advisory))
        fixed = re.search(r"Not vulnerable: ([^<]+)", advisory)
        vulnerable = re.search(r"Vulnerable: ([^<]+)", advisory)
        if not ids or not fixed or not vulnerable:
            continue
        published_ranges = re.findall(rf"({VERSION})-({VERSION})", vulnerable[1])
        if not any(version_tuple(old) <= version_tuple(approved) <= version_tuple(new)
                   for old, new in published_ranges):
            continue
        versions = [version_tuple(v) for v in re.findall(rf"({VERSION})\+", fixed[1])]
        if not any(v[:2] == line(candidate) and v <= version_tuple(candidate) for v in versions):
            continue
        approved_fixes = [v for v in versions if v[:2] == line(approved)]
        if not approved_fixes:
            candidate_only.update(ids)
        elif min(approved_fixes) > version_tuple(approved):
            fix = ".".join(map(str, min(approved_fixes)))
            shared.update(f"{cve} is also fixed by approved-line {fix}" for cve in ids)
    return sorted(shared), sorted(candidate_only)


def image_variants(manifest, runtime, version):
    records = [record for record in manifest.split("\n\n") if record.startswith("Tags: ")]
    if not records:
        raise ValueError(f"Missing Docker Official Images records for {runtime}")
    variants = {}
    prefix = version + ("-fpm-" if runtime == "php" else "-")
    for record in records:
        fields = dict(row.split(": ", 1) for row in record.splitlines() if ": " in row)
        for tag in fields["Tags"].split(", "):
            if not tag.startswith(prefix):
                continue
            commit = fields.get("GitCommit", "")
            architectures = fields.get("Architectures", "").split(", ")
            if (not re.fullmatch(r"[0-9a-z.-]+", tag) or
                    not re.fullmatch(r"[a-f0-9]{40}", commit) or
                    not all(re.fullmatch(r"[a-z0-9]+", arch) for arch in architectures) or tag in variants):
                raise ValueError(f"Invalid official image record for {runtime} {version}")
            variants[tag] = [tag, sorted(architectures), commit]
    return sorted(variants.values())


def collect(containerfile, get=read, today=None):
    pins = baseline(containerfile)
    php_versions = php_support(get(PHP_SUPPORT), today or date.today())
    nginx = nginx_releases(get(NGINX_DOWNLOADS))
    nginx_advisories = get(NGINX_ADVISORIES)
    manifests = {runtime: get(IMAGES + runtime) for runtime in pins}
    opportunities = []
    php_pin = pins["php"][0]
    approved_php_support = php_versions.get(".".join(php_pin.split(".")[:2]))
    for branch, dates in sorted(php_versions.items(), key=lambda item: line(item[0])):
        if line(branch) <= line(php_pin):
            continue
        version, checksum, security = php_release(get(PHP_RELEASE + branch), branch)
        changes = f"https://www.php.net/ChangeLog-{branch.split('.')[0]}.php"
        opportunities.append(dict(
            runtime="php", channel="supported", version=version, source_sha256=checksum,
            archive=f"https://www.php.net/distributions/php-{version}.tar.gz",
            support=f"Active until {dates[0]}; security until {dates[1]}",
            security=("Upstream marks this release as a security release."
                      if security else "Review the upstream release changelog for security fixes.")
                     + (f" Approved line security support ends {approved_php_support[1]}."
                        if approved_php_support else " The approved line is absent from the supported list."),
            security_signal={"security_release": security,
                             "approved_security_until": approved_php_support[1] if approved_php_support else None},
            advisories=changes, changes=changes,
            compatibility=f"https://www.php.net/manual/migration{branch.replace('.', '')}.php",
        ))
    for channel, version in nginx.items():
        if line(version) <= line(pins["nginx"][0]):
            continue
        branch = ".".join(version.split(".")[:2])
        changes = "https://nginx.org/en/CHANGES" + (f"-{branch}" if channel == "Stable" else "")
        archive = f"https://nginx.org/download/nginx-{version}.tar.gz"
        backports, candidate_only = nginx_fix_comparison(nginx_advisories, pins["nginx"][0], version)
        security = backports + [
            f"{cve} has a listed fix in this release; the advisory does not list an approved-line fix"
            for cve in candidate_only
        ]
        opportunities.append(dict(
            runtime="nginx", channel=channel.lower(), version=version, archive=archive,
            signature=archive + ".asc",
            support=f"Current upstream {channel.lower()} channel; upstream does not publish an EOL date here",
            security=(". ".join(security) + "." if security else
                      "Review published advisories for applicability and same-line alternatives."),
            security_signal={"same_line_fixes": backports, "candidate_only_fixes": candidate_only},
            changes=changes, compatibility=changes, advisories=NGINX_ADVISORIES,
        ))
    for row in opportunities:
        runtime = row["runtime"]
        row["approved_variant"] = pins[runtime][1]
        row["variants"] = image_variants(manifests[runtime], runtime, row["version"])
    return opportunities


def ready(row):
    expected = row["version"] + row["approved_variant"]
    return any(tag == expected and NATIVE <= set(arch) for tag, arch, _ in row["variants"])


def key(row):
    # Report actual line, support and compatibility milestones before repeating patch notices.
    fields = [row["runtime"], line(row["version"]), row["channel"], row["support"],
              row["approved_variant"], ready(row), row["security_signal"]]
    return sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()


def render(rows):
    if not rows:
        return ""
    body = ["## Runtime upgrade opportunities", "",
            "Discovery evidence only. Runtime admission and publication use their existing gates.", ""]
    for row in rows:
        runtime, version = row["runtime"], row["version"]
        archive = f"- [Official source archive]({row['archive']})"
        if runtime == "php":
            archive += f" · SHA-256 {row['source_sha256']}"
        else:
            archive += f" · [Upstream signature]({row['signature']})"
        body.extend([f"### {runtime.upper()} {version} ({row['channel']})", "",
                     f"<!-- {MARKER}{key(row)} -->", archive,
                     f"- Support — {row['support']}.",
                     f"- {row['security']} [Official security history]({row['advisories']})",
                     f"- [Release changes]({row['changes']}) · [Compatibility reference]({row['compatibility']})",
                     "- Qualification to plan — native AMD64 and ARM64, FPM extensions and Composer on PHP, "
                     "HTTP and proxy configuration on Nginx, and existing paired artifact-security checks.",
                     f"- Like-for-like variant {version + row['approved_variant']} on both architectures — "
                     + ("advertised." if ready(row) else "unavailable in the official image index.")])
        for tag, arch, commit in row["variants"]:
            body.append(f"  - {tag} ({', '.join(arch)}) · [official image source]({IMAGE_SOURCE[runtime]}{commit})")
        if not row["variants"]:
            body.append("  - No advertised exact variant for this release.")
        body.append("")
    return "\n".join(body)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    parser = cli.add_subparsers(dest="command", required=True)
    scan = parser.add_parser("scan")
    scan.add_argument("containerfile", type=Path)
    report = parser.add_parser("report")
    report.add_argument("data", type=Path)
    report.add_argument("--seen", type=Path)
    args = cli.parse_args()
    if args.command == "scan":
        print(json.dumps(collect(args.containerfile)))
        return
    rows = json.loads(args.data.read_text())
    if args.seen:
        seen = set(re.findall(rf"^<!-- {MARKER}({SHA}) -->$", args.seen.read_text(), re.M))
        rows = [row for row in rows if key(row) not in seen]
    print(render(rows), end="")


if __name__ == "__main__":
    main()
