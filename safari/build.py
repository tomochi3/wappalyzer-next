"""Build the Safari version of the bundled Wappalyzer extension (macOS only).

Safari runs web extensions only from inside a macOS app, so this wraps the
same on-demand extension the Chrome instructions use
(wappalyzer/data/wappalyzer-extension.zip) in an app with Xcode's
safari-web-extension-converter and builds it.

    python3 safari/build.py                 # signed to run on this Mac only
    python3 safari/build.py --team ABCDE12345   # signed with your Apple ID team

The app is written to build/safari/Wappalyzer Next.app.
"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
EXTENSION_ARCHIVE = REPO_ROOT / "wappalyzer" / "data" / "wappalyzer-extension.zip"
OUTPUT_DIR = REPO_ROOT / "build" / "safari"
APP_NAME = "Wappalyzer Next"
BUNDLE_ID = "io.github.tomochi3.Wappalyzer-Next"
# Safari 16.4 is the first to run Manifest V3 extensions with this API set
DEPLOYMENT_TARGET = "13.3"

# Safari has no downloads API, so "Export as CSV" saves through a link instead
DOWNLOAD_CSV = """    const granted = await promisify(chrome.permissions, 'request', {
      permissions: ['downloads'],
    })
"""
DOWNLOAD_CSV_SAFARI = """    if (!chrome.downloads) {
      const link = document.createElement('a')

      link.href = file
      link.download = filename
      document.body.appendChild(link)
      link.click()
      link.remove()

      return false
    }

""" + DOWNLOAD_CSV


def patch_popup_js(content):
    if DOWNLOAD_CSV not in content:
        raise RuntimeError("Failed to patch CSV export in js/popup.js")

    return content.replace(DOWNLOAD_CSV, DOWNLOAD_CSV_SAFARI, 1)


def patch_manifest(manifest):
    # the same checks as the Chrome build: never read pages on its own
    if manifest.get("content_scripts") or manifest.get("host_permissions"):
        raise RuntimeError("The bundled extension is not the on-demand build")

    if {"tabs", "webRequest"} & set(manifest.get("permissions", [])):
        raise RuntimeError("The bundled extension is not the on-demand build")

    manifest.pop("minimum_chrome_version", None)
    optional = [p for p in manifest.get("optional_permissions", []) if p != "downloads"]

    if optional:
        manifest["optional_permissions"] = optional
    else:
        manifest.pop("optional_permissions", None)

    return manifest


def prepare_extension(extension_dir):
    with zipfile.ZipFile(EXTENSION_ARCHIVE) as archive:
        archive.extractall(extension_dir)

    # signature of the Firefox package, which no longer matches after patching
    shutil.rmtree(extension_dir / "META-INF", ignore_errors=True)

    popup = extension_dir / "js" / "popup.js"
    popup.write_text(patch_popup_js(popup.read_text(encoding="utf-8")), encoding="utf-8")

    manifest_path = extension_dir / "manifest.json"
    manifest = patch_manifest(json.loads(manifest_path.read_text(encoding="utf-8")))
    manifest_path.write_text(json.dumps(manifest, separators=(",", ":")), encoding="utf-8")

    return manifest["version"]


def run(command, **kwargs):
    print("+", " ".join(f'"{part}"' if " " in part else part for part in command), flush=True)
    subprocess.run(command, check=True, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--team",
        help="Apple Developer team ID to sign with (a free Apple ID works). "
        "Without it the app is signed to run on this Mac only, and Safari "
        "needs 'Allow Unsigned Extensions' after every restart.",
    )
    args = parser.parse_args()

    if sys.platform != "darwin":
        sys.exit("The Safari version can only be built on macOS.")

    if not shutil.which("xcrun") or subprocess.run(
        ["xcrun", "--find", "safari-web-extension-converter"], capture_output=True
    ).returncode:
        sys.exit("Xcode is required: install it from the App Store, then run "
                 "'sudo xcode-select -s /Applications/Xcode.app'.")

    with tempfile.TemporaryDirectory(prefix="wappalyzer-safari-") as tempdir:
        tempdir = Path(tempdir)
        extension_dir = tempdir / "extension"
        project_dir = tempdir / "project"
        derived_dir = tempdir / "derived"

        version = prepare_extension(extension_dir)

        run([
            "xcrun", "safari-web-extension-converter", str(extension_dir),
            "--project-location", str(project_dir),
            "--app-name", APP_NAME,
            "--bundle-identifier", BUNDLE_ID,
            "--swift", "--macos-only", "--copy-resources",
            "--no-open", "--no-prompt", "--force",
        ], stdout=subprocess.DEVNULL)

        signing = (
            ["CODE_SIGN_STYLE=Automatic", f"DEVELOPMENT_TEAM={args.team}", "-allowProvisioningUpdates"]
            if args.team
            else ["CODE_SIGN_STYLE=Manual", "CODE_SIGN_IDENTITY=-", "DEVELOPMENT_TEAM="]
        )

        run([
            "xcodebuild",
            "-project", str(project_dir / APP_NAME / f"{APP_NAME}.xcodeproj"),
            "-scheme", APP_NAME,
            "-configuration", "Release",
            "-derivedDataPath", str(derived_dir),
            "-quiet",
            f"MACOSX_DEPLOYMENT_TARGET={DEPLOYMENT_TARGET}",
            f"MARKETING_VERSION={version}",
            "ARCHS=arm64 x86_64",
            "ONLY_ACTIVE_ARCH=NO",
            *signing,
            "build",
        ])

        app = OUTPUT_DIR / f"{APP_NAME}.app"
        shutil.rmtree(app, ignore_errors=True)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        # ditto keeps the code signature intact
        run(["ditto", str(derived_dir / "Build" / "Products" / "Release" / f"{APP_NAME}.app"), str(app)])

    print(f"\nBuilt {app}")
    print("Next: open the app once, then enable the extension in Safari > Settings > Extensions.")

    if not args.team:
        print("Unsigned build: first turn on Safari > Develop > Allow Unsigned Extensions "
              "(needed again after every Safari restart).")


if __name__ == "__main__":
    main()
