"""Open a generated page through file:// in a headless browser and check the media really works.

Plays the first voice note (its time must advance), loads a photo and a video, checks
localStorage, and saves a screenshot of the voice note. Prints a JSON summary.

Usage: python tools/dev/page_check.py PAGE.html SHOT.png
"""

import base64
import json
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cdpws import WS, find_browser  # noqa: E402

PORT = 9337
CHECK = r"""
(async () => {
  const out = {protocol: location.protocol, lang: document.documentElement.lang};
  const v = document.querySelector('.msg.k-voice .voice');
  if (v) {
    v.scrollIntoView({block: 'center'});
    v.querySelector('.v-play').click();
    await new Promise(r => setTimeout(r, 2500));
    const a = v._audio;
    out.voice = {currentTime: a && +a.currentTime.toFixed(2), duration: a && a.duration,
                 error: a && a.error && a.error.code, errorShown: v.classList.contains('error')};
  }
  const img = document.querySelector('.msg.k-image img');
  if (img) { img.scrollIntoView({block: 'center'}); await new Promise(r => setTimeout(r, 1500));
             out.image = {loaded: img.naturalWidth > 0}; }
  const vid = document.querySelector('.msg.k-video video');
  if (vid) { vid.scrollIntoView({block: 'center'}); await new Promise(r => setTimeout(r, 2500));
             out.video = {readyState: vid.readyState}; }
  try { localStorage.setItem('wa2html:check', '1'); out.localStorage = localStorage.getItem('wa2html:check') === '1'; }
  catch (e) { out.localStorage = String(e); }
  if (v) { v.scrollIntoView({block: 'center'}); await new Promise(r => setTimeout(r, 300)); }
  return JSON.stringify(out);
})()
"""


def main() -> None:
    page = Path(sys.argv[1]).resolve()
    shot = Path(sys.argv[2])
    profile = tempfile.mkdtemp(prefix="wa2html-browser-")
    browser = subprocess.Popen([find_browser(), "--headless=new", "--disable-gpu", "--no-first-run",
                                f"--remote-debugging-port={PORT}", f"--user-data-dir={profile}",
                                "--autoplay-policy=no-user-gesture-required", "--window-size=900,700", "about:blank"])
    try:
        for _ in range(50):
            try:
                targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json"))
                break
            except OSError:
                time.sleep(0.2)
        ws = WS(next(t for t in targets if t["type"] == "page")["webSocketDebuggerUrl"])
        ws.call("Page.enable")
        ws.call("Page.navigate", url=page.as_uri())
        for _ in range(240):  # big single-file pages take a while to parse
            state = ws.call("Runtime.evaluate", expression="document.readyState")
            if state.get("result", {}).get("result", {}).get("value") == "complete":
                break
            time.sleep(0.5)
        result = ws.call("Runtime.evaluate", expression=CHECK, awaitPromise=True, returnByValue=True)
        print(result.get("result", {}).get("result", {}).get("value") or result)
        data = ws.call("Page.captureScreenshot", format="png")["result"]["data"]
        shot.write_bytes(base64.b64decode(data))
        print("screenshot:", shot)
    finally:
        browser.terminate()
        if sys.platform == "win32":  # the browser leaves child processes behind
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(browser.pid)], capture_output=True)


if __name__ == "__main__":
    main()
