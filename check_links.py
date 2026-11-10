"""Checks every link in index.html and writes a short report.

Runs once a month in the "Publish site" workflow. The run is marked as failed only when
a link is clearly broken (page not found, or the site no longer exists), so GitHub emails you.
Sites that refuse automated visitors are listed separately, to check by hand if you wish.
"""
import concurrent.futures, html, os, re, socket, sys, urllib.error, urllib.request

SKIP = ("https://schema.org", "http://www.w3.org", "https://www.w3.org", "https://fedezonzi.github.io")
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
BLOCKED = {401, 403, 405, 406, 429, 999}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def collect(page):
    found = set()
    page = re.sub(r"/\*.*?\*/", "", page, flags=re.S)   # ignore examples written in comments
    for u in re.findall(r"""https?://[^\s"'<>`\\)]+""", page):
        u = html.unescape(u).rstrip(".,;:")
        if not u.startswith(SKIP):
            found.add(u)
    for doi in re.findall(r"""\bdoi:\s*"([^"]+)\"""", page):
        found.add("https://doi.org/" + doi)
    return sorted(found)


def check(url):
    """Returns (url, verdict, detail); verdict is ok, broken, blocked or unsure."""
    doi = url.startswith("https://doi.org/")
    opener = urllib.request.build_opener(NoRedirect) if doi else urllib.request.build_opener()
    last = ""
    for method in ("HEAD", "GET"):
        req = urllib.request.Request(url, method=method, headers={"User-Agent": UA, "Accept": "text/html,*/*"})
        try:
            with opener.open(req, timeout=25) as r:
                return url, "ok", str(r.status)
        except urllib.error.HTTPError as e:
            if doi and 300 <= e.code < 400:
                return url, "ok", f"DOI registered ({e.code})"
            if e.code in (404, 410):
                if method == "HEAD":
                    last = str(e.code); continue
                return url, "broken", f"page not found ({e.code})"
            if e.code in BLOCKED:
                if method == "HEAD":
                    last = str(e.code); continue
                return url, "blocked", f"the site refuses automated visits ({e.code})"
            last = f"server error ({e.code})"
        except urllib.error.URLError as e:
            reason = e.reason
            if isinstance(reason, socket.gaierror):
                return url, "broken", "the site no longer exists (address not found)"
            last = f"could not connect ({reason})"
        except Exception as e:  # timeouts and unusual errors
            last = f"could not connect ({e})"
    return url, "unsure", last


def main():
    page = open("index.html", encoding="utf-8").read()
    urls = collect(page)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(check, urls))
    groups = {k: [r for r in results if r[1] == k] for k in ("broken", "unsure", "blocked", "ok")}
    lines = [f"## Link check: {len(urls)} links",
             f"{len(groups['ok'])} working, {len(groups['broken'])} broken, "
             f"{len(groups['unsure'])} to retry, {len(groups['blocked'])} not checkable automatically", ""]
    titles = {"broken": "Broken links: please fix these in index.html",
              "unsure": "Links that did not answer this time (often temporary)",
              "blocked": "Sites that refuse automated checks (usually fine)"}
    for k, title in titles.items():
        if groups[k]:
            lines += [f"### {title}", ""] + [f"- {u} : {d}" for u, _, d in groups[k]] + [""]
    report = "\n".join(lines)
    print(report)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(report + "\n")
    sys.exit(1 if groups["broken"] else 0)


if __name__ == "__main__":
    main()
