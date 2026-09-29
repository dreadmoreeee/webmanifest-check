"""Optional headless Chromium probe. Loads the page once; never clicks or types."""

from .checks import Report

_JS = """async () => {
  const sw = 'serviceWorker' in navigator;
  const regs = sw ? await navigator.serviceWorker.getRegistrations() : [];
  return {
    supported: sw,
    registrations: regs.map(r => r.scope),
    controller: !!(sw && navigator.serviceWorker.controller),
    secure: window.isSecureContext,
    installPromptSeen: !!window.__wmcInstallPrompt,
  };
}"""

_INIT = "window.addEventListener('beforeinstallprompt', () => { window.__wmcInstallPrompt = true; });"


def check_browser(rep: Report, url: str) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError("--browser needs Playwright: pip install playwright && playwright install chromium") from None
    with sync_playwright() as p:
        try:
            b = p.chromium.launch(headless=True)
        except Exception as e:
            raise RuntimeError(f"cannot start Chromium ({str(e).splitlines()[0]}); run: playwright install chromium") from None
        try:
            page = b.new_context().new_page()
            page.add_init_script(_INIT)
            page.goto(url, wait_until="load", timeout=30000)
            page.wait_for_timeout(3000)
            info = page.evaluate(_JS)
        finally:
            b.close()
    rep.browser = info
    if not info["supported"] or not info["secure"]:
        rep.add("warning", "browser-secure", "page is not a secure context; service workers and install are unavailable")
    if info["registrations"]:
        rep.add("ok", "browser-sw", "service worker registered: " + ", ".join(info["registrations"]))
        if not info["controller"]:
            rep.add("info", "browser-sw-controller", "a service worker is registered but is not controlling this load (normal on a first visit)")
    else:
        rep.add("warning", "browser-sw", "no service worker registered (needed for offline support; Chrome no longer requires one to install)")
    if info["installPromptSeen"]:
        rep.add("ok", "browser-install", "Chromium fired beforeinstallprompt: installable")
    else:
        rep.add("info", "browser-install", "beforeinstallprompt not observed within 3 s (headless Chromium may not fire it; not proof of failure)")
