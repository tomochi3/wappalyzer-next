import hashlib
import json
import re
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path


URL = "https://addons.mozilla.org/firefox/downloads/latest/wappalyzer/platform:2/wappalyzer.xpi"
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "wappalyzer" / "data"
EXTENSION_ARCHIVE = DATA_DIR / "wappalyzer-extension.zip"
README = REPO_ROOT / "README.md"
README_CHECKSUM = re.compile(r"(SHA-256: `)[0-9a-f]{64}(`)")
ONDEMAND_SCRIPT = REPO_ROOT / ".github" / "extension" / "ondemand.js"

# What upstream uses to analyse every page automatically. The Chrome build
# drops it in favour of activeTab; the CLI (wappalyzer/browser/analyzer.py,
# AUTOMATIC_MODE) puts the same entries back, so they must stay in sync.
AUTOMATIC_CONTENT_SCRIPTS = [
    {"matches": ["http://*/*", "https://*/*"], "js": ["js/content.js"], "run_at": "document_idle"}
]
AUTOMATIC_PERMISSIONS = {"tabs", "webRequest"}
ALL_SITES = ["http://*/*", "https://*/*"]
ONDEMAND_PERMISSIONS = {"activeTab", "scripting"}

WEBREQUEST_LISTENERS = re.compile(
    r"^chrome\.webRequest\.onResponseStarted\.addListener\(.*?types: \['xmlhttprequest'\],\n\}\)\n",
    re.MULTILINE | re.DOTALL,
)

PROMPT_BLOCK = re.compile(
    r"^[ \t]*const current = await get(?:Cached)?Option\('version'\)\n"
    r".*?"
    r"(?=^[ \t]*(?:\} catch\b|\} finally\b|initDone\(\)))",
    re.MULTILINE | re.DOTALL,
)


TRACKING_DEFAULT_ON = "getCachedOption('tracking', true)"


def patch_index_js(content):
    content = PROMPT_BLOCK.sub("", content, count=1)

    if "https://www.wappalyzer.com/installed/" in content:
        raise RuntimeError("Failed to remove install prompt from js/index.js")

    if "https://www.wappalyzer.com/upgraded/" in content:
        raise RuntimeError("Failed to remove upgrade prompt from js/index.js")

    # don't report visited hostnames to wappalyzer.com unless the user opts in
    if TRACKING_DEFAULT_ON not in content:
        raise RuntimeError("Failed to turn tracking off by default in js/index.js")

    content = content.replace(TRACKING_DEFAULT_ON, "getCachedOption('tracking', false)")

    # the on-demand build has no webRequest permission, where registering
    # these listeners would throw and stop the service worker
    content, count = WEBREQUEST_LISTENERS.subn(
        lambda m: "if (chrome.webRequest) {\n" + m.group(0) + "}\n", content, count=1
    )

    if count != 1:
        raise RuntimeError("Failed to guard webRequest listeners in js/index.js")

    return content


def patch_popup_html(content):
    tag = '<script src="../js/popup.js"></script>'

    if tag not in content:
        raise RuntimeError("Failed to add on-demand script to html/popup.html")

    return content.replace(tag, tag + '\n    <script src="../js/ondemand.js"></script>', 1)


def patch_options_js(content):
    if "['tracking', true]" not in content:
        raise RuntimeError("Failed to turn tracking off by default in js/options.js")

    return content.replace("['tracking', true]", "['tracking', false]")


def patch_manifest_for_chromium(manifest):
    manifest = json.loads(json.dumps(manifest))
    manifest.pop("browser_specific_settings", None)
    manifest.pop("applications", None)

    background = manifest.get("background")

    if isinstance(background, dict) and background.get("service_worker"):
        background.pop("scripts", None)

    # on-demand: read a tab only when the user opens the popup on it
    if manifest.get("content_scripts") != AUTOMATIC_CONTENT_SCRIPTS:
        raise RuntimeError("Upstream content_scripts changed; update AUTOMATIC_CONTENT_SCRIPTS and the CLI")

    if sorted(manifest.get("host_permissions", [])) != sorted(ALL_SITES):
        raise RuntimeError("Upstream host_permissions changed; update ALL_SITES and the CLI")

    manifest.pop("content_scripts")
    manifest.pop("host_permissions")
    permissions = set(manifest.get("permissions", [])) - AUTOMATIC_PERMISSIONS
    manifest["permissions"] = sorted(permissions | ONDEMAND_PERMISSIONS)

    return manifest


def validate_manifest(manifest):
    errors = []

    if manifest.get("manifest_version") != 3:
        errors.append("manifest_version must be 3")

    if manifest.get("action", {}).get("default_popup") != "html/popup.html":
        errors.append("action.default_popup must be html/popup.html")

    if not manifest.get("background", {}).get("service_worker"):
        errors.append("background.service_worker is required")

    if "scripts" in manifest.get("background", {}):
        errors.append("background.scripts must be removed for Chromium MV3")

    permissions = set(manifest.get("permissions", []))

    for permission in ("activeTab", "scripting", "cookies", "storage"):
        if permission not in permissions:
            errors.append(f"missing permission: {permission}")

    for permission in AUTOMATIC_PERMISSIONS & permissions:
        errors.append(f"on-demand build must not request: {permission}")

    if manifest.get("host_permissions"):
        errors.append("on-demand build must not request host_permissions")

    if manifest.get("content_scripts"):
        errors.append("on-demand build must not have content_scripts")

    if "browser_specific_settings" in manifest:
        errors.append("browser_specific_settings must be removed")

    if "applications" in manifest:
        errors.append("applications must be removed")

    if errors:
        raise RuntimeError("Invalid Chromium extension manifest: " + "; ".join(errors))


def validate_extension_tree(extension_dir, require_technologies=False):
    required_files = (
        "manifest.json",
        "html/popup.html",
        "js/background.js",
        "js/index.js",
        "js/content.js",
        "js/ondemand.js",
    )

    for relative_path in required_files:
        if not (extension_dir / relative_path).is_file():
            raise RuntimeError(f"Missing extension file: {relative_path}")

    if require_technologies and not any((extension_dir / "technologies").glob("*.json")):
        raise RuntimeError("Missing extension technology fingerprint files")

    validate_manifest(json.loads((extension_dir / "manifest.json").read_text(encoding="utf-8")))


def write_chromium_extension_archive(extension_dir, archive_path):
    manifest_path = extension_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            patch_manifest_for_chromium(
                json.loads(manifest_path.read_text(encoding="utf-8"))
            ),
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    validate_extension_tree(extension_dir, require_technologies=True)

    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(extension_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(extension_dir))


def patch_extension_tree(extension_dir):
    for name, patch in (
        ("js/index.js", patch_index_js),
        ("js/options.js", patch_options_js),
        ("html/popup.html", patch_popup_html),
    ):
        path = extension_dir / name
        path.write_text(patch(path.read_text(encoding="utf-8")), encoding="utf-8")

    shutil.copy2(ONDEMAND_SCRIPT, extension_dir / "js" / "ondemand.js")


def update_readme_checksum():
    digest = hashlib.sha256(EXTENSION_ARCHIVE.read_bytes()).hexdigest()
    content = README.read_text(encoding="utf-8")
    updated, count = README_CHECKSUM.subn(rf"\g<1>{digest}\g<2>", content)

    if count != 1:
        raise RuntimeError("README.md must contain exactly one extension SHA-256 line")

    README.write_text(updated, encoding="utf-8")


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="wappalyzer-update-") as tempdir:
        tempdir = Path(tempdir)
        archive_path = tempdir / "wappalyzer.xpi"
        extract_dir = tempdir / "wappalyzer"

        urllib.request.urlretrieve(URL, archive_path)
        # record what was bundled so the update can be checked against AMO
        print(f"sha256 {hashlib.sha256(archive_path.read_bytes()).hexdigest()}  {URL}")

        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(extract_dir)

        patch_extension_tree(extract_dir)

        technologies = {}
        for path in sorted((extract_dir / "technologies").glob("*.json")):
            technologies.update(json.loads(path.read_text(encoding="utf-8")))

        (DATA_DIR / "technologies.json").write_text(
            json.dumps(technologies, indent=4) + "\n",
            encoding="utf-8",
        )
        shutil.copy2(extract_dir / "groups.json", DATA_DIR / "groups.json")
        shutil.copy2(extract_dir / "categories.json", DATA_DIR / "categories.json")

        write_chromium_extension_archive(extract_dir, EXTENSION_ARCHIVE)

    update_readme_checksum()


if __name__ == "__main__":
    main()
