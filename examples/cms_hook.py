"""Example: a CMS pre-publish hook that asks Preflight before anything goes live.

    PREFLIGHT_URL=https://<your-backend> PREFLIGHT_API_KEY=pf_live_... \
        python examples/cms_hook.py "PayWise is 100% secure!" linkedin

Exit code 0 = safe to publish, 1 = blocked by a critical finding, 2 = Preflight unreachable
(fail closed: do not publish unchecked content).
"""

import json
import os
import sys
import urllib.error
import urllib.request


def preflight(content: str, channel: str) -> dict:
    request = urllib.request.Request(
        f"{os.environ['PREFLIGHT_URL'].rstrip('/')}/api/v1/preflight",
        data=json.dumps({"content": content, "channel": channel}).encode(),
        headers={"Content-Type": "application/json", "X-API-Key": os.environ["PREFLIGHT_API_KEY"]},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def main() -> int:
    content = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read()
    channel = sys.argv[2] if len(sys.argv) > 2 else "linkedin"
    try:
        result = preflight(content, channel)
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"Preflight unreachable ({exc}); not publishing.", file=sys.stderr)
        return 2

    print(f"Brand Score {result['brand_score']['score']}/100")
    for finding in result["findings"]:
        if finding["needs_review"]:
            continue
        suggestion = finding["suggestion"]["text"] if finding["suggestion"] else "-"
        print(f"  [{finding['severity']:8}] {finding['rule']['id']}: \"{finding['text']}\" -> {suggestion}")
    if result["blocking"]:
        print("Blocked: fix the critical findings in Preflight, then publish.")
        return 1
    print("Cleared for publication. A human approval in Preflight is still recommended.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
