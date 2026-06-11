#!/usr/local/autopkg/python
#
# NSURLSessionDownloader.py
#
# A drop-in replacement for URLDownloader for URLs behind Cloudflare's JS
# challenge, which blocks curl by TLS fingerprint. Apple's native network
# stack (NSURLSession) passes the challenge, so the download is performed
# via osascript/JXA, which needs no tooling beyond stock macOS.
#
# Mimics URLDownloader's behavior: stores ETag/Last-Modified in extended
# attributes on the downloaded file and sends If-None-Match /
# If-Modified-Since on subsequent runs, so download_changed is False when
# the server answers 304.

import json
import os
import subprocess
import tempfile

import xattr
from autopkglib import Processor, ProcessorError

__all__ = ["NSURLSessionDownloader"]

XATTR_ETAG = "com.github.autopkg.etag"
XATTR_LAST_MODIFIED = "com.github.autopkg.last-modified"

JXA_SOURCE = r"""
ObjC.import('Cocoa');

function run(argv) {
    const url = $.NSURL.URLWithString(argv[0]);
    const dest = argv[1];
    const headers = JSON.parse(argv[2]);
    const req = $.NSMutableURLRequest.requestWithURL(url);
    for (const field in headers) {
        // ObjC selector is setValue:forHTTPHeaderField: — value comes first.
        req.setValueForHTTPHeaderField(headers[field], field);
    }
    let done = false;
    let result = {};
    const task = $.NSURLSession.sharedSession.downloadTaskWithRequestCompletionHandler(req, (loc, resp, err) => {
        if (!err.isNil()) {
            result = {error: ObjC.unwrap(err.localizedDescription)};
        } else {
            const code = Number(resp.statusCode);
            result = {status: code, headers: ObjC.deepUnwrap(resp.allHeaderFields) || {}};
            if (code === 200) {
                const fm = $.NSFileManager.defaultManager;
                fm.removeItemAtPathError(dest, null);
                if (!fm.moveItemAtPathToPathError(ObjC.unwrap(loc.path), dest, null)) {
                    result = {error: 'could not move downloaded file to ' + dest};
                }
            }
        }
        done = true;
    });
    task.resume;
    const runLoop = $.NSRunLoop.currentRunLoop;
    while (!done) {
        runLoop.runUntilDate($.NSDate.dateWithTimeIntervalSinceNow(0.25));
    }
    return JSON.stringify(result);
}
"""


class NSURLSessionDownloader(Processor):
    """Downloads a URL using NSURLSession (via osascript/JXA) instead of
    curl, for servers whose Cloudflare protection rejects curl's TLS
    fingerprint. Output variables match URLDownloader."""

    description = __doc__
    input_variables = {
        "url": {
            "required": True,
            "description": "The URL to download.",
        },
        "filename": {
            "required": False,
            "description": "Filename to override the URL's tail.",
        },
        "download_dir": {
            "required": False,
            "description": (
                "Directory to store the file in. Defaults to "
                "%RECIPE_CACHE_DIR%/downloads."
            ),
        },
        "request_timeout": {
            "required": False,
            "description": "Timeout for the osascript download in seconds. "
            "Defaults to 600.",
        },
    }
    output_variables = {
        "pathname": {"description": "Path to the downloaded file."},
        "last_modified": {
            "description": "Last-Modified header from the server, if any."
        },
        "etag": {"description": "ETag header from the server, if any."},
        "download_changed": {
            "description": (
                "Boolean indicating if the download has changed since the "
                "last time it was downloaded."
            )
        },
        "url_downloader_summary_result": {
            "description": "Description of interesting results."
        },
    }

    def get_xattr(self, path, attr):
        try:
            return xattr.getxattr(path, attr).decode("utf-8")
        except OSError:
            return None

    def main(self):
        download_dir = self.env.get("download_dir") or os.path.join(
            self.env["RECIPE_CACHE_DIR"], "downloads"
        )
        filename = self.env.get("filename") or os.path.basename(
            self.env["url"].rstrip("/")
        )
        pathname = os.path.join(download_dir, filename)
        self.env["pathname"] = pathname
        self.env["download_changed"] = False
        self.env["last_modified"] = ""
        self.env["etag"] = ""
        os.makedirs(download_dir, exist_ok=True)

        # Ask for a 304 if we already have a copy with cached validators.
        request_headers = {}
        if os.path.isfile(pathname):
            etag = self.get_xattr(pathname, XATTR_ETAG)
            last_modified = self.get_xattr(pathname, XATTR_LAST_MODIFIED)
            if etag:
                request_headers["If-None-Match"] = etag
            if last_modified:
                request_headers["If-Modified-Since"] = last_modified

        temp_pathname = pathname + ".download"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".js", delete=False
        ) as jxa_file:
            jxa_file.write(JXA_SOURCE)
        try:
            proc = subprocess.run(
                [
                    "/usr/bin/osascript",
                    "-l",
                    "JavaScript",
                    jxa_file.name,
                    self.env["url"],
                    temp_pathname,
                    json.dumps(request_headers),
                ],
                capture_output=True,
                text=True,
                timeout=int(self.env.get("request_timeout", 600)),
            )
        except subprocess.TimeoutExpired:
            raise ProcessorError(f"Download of {self.env['url']} timed out")
        finally:
            os.unlink(jxa_file.name)

        if proc.returncode != 0:
            raise ProcessorError(
                f"osascript download failed: {proc.stderr.strip()}"
            )
        try:
            result = json.loads(proc.stdout)
        except json.JSONDecodeError:
            raise ProcessorError(
                f"Unexpected osascript output: {proc.stdout.strip()}"
            )
        if "error" in result:
            raise ProcessorError(f"Download failed: {result['error']}")

        status = result["status"]
        response_headers = {
            key.lower(): value for key, value in result["headers"].items()
        }

        if status == 304:
            self.env["etag"] = request_headers.get("If-None-Match", "")
            self.env["last_modified"] = request_headers.get(
                "If-Modified-Since", ""
            )
            self.output(f"Item at URL is unchanged. Using existing {pathname}")
            return

        if status != 200:
            raise ProcessorError(
                f"Server returned HTTP {status} for {self.env['url']}"
            )
        if not os.path.getsize(temp_pathname):
            raise ProcessorError("Downloaded file is empty")

        os.rename(temp_pathname, pathname)
        self.env["download_changed"] = True
        self.env["etag"] = response_headers.get("etag", "")
        self.env["last_modified"] = response_headers.get("last-modified", "")
        if self.env["etag"]:
            xattr.setxattr(
                pathname, XATTR_ETAG, self.env["etag"].encode("utf-8")
            )
        if self.env["last_modified"]:
            xattr.setxattr(
                pathname,
                XATTR_LAST_MODIFIED,
                self.env["last_modified"].encode("utf-8"),
            )
        self.output(f"Downloaded {pathname}")
        self.env["url_downloader_summary_result"] = {
            "summary_text": "The following new items were downloaded:",
            "data": {"download_path": pathname},
        }


if __name__ == "__main__":
    PROCESSOR = NSURLSessionDownloader()
    PROCESSOR.execute_shell()
