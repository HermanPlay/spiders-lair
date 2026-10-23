(function () {
  const DEBUG = false;
  const log = (...a) => { if (DEBUG) console.debug("[door-check]", ...a); };

  function readJson(id, fallback) {
    try { return JSON.parse(document.getElementById(id).textContent); }
    catch { return fallback; }
  }

  function pickUA(result) {
    if (!result || typeof result !== "object") return null;
    return (
      result.ua ||
      result.userAgent ||
      result["user-agent"] ||
      result?.headers?.["user-agent"] ||
      result?.headers?.userAgent ||
      result?.request?.headers?.["user-agent"] ||
      result?.request?.headers?.userAgent ||
      null
    );
  }

  function parseUAClaim(ua) {
    if (!ua || typeof ua !== "string") return { family: "unknown", engine: "unknown" };
    const s = ua;

    if (/CriOS\/\d+/.test(s)) return { family: "chrome", engine: "webkit" };
    if (/FxiOS\/\d+/.test(s)) return { family: "firefox", engine: "webkit" };

    if (/Edg(?:A|iOS)?\/\d+/.test(s)) return { family: "edge", engine: "chromium" };
    if (/OPR\/\d+/.test(s) || /Opera\/\d+/.test(s)) return { family: "opera", engine: "chromium" };
    if (/Chrom(?:e|ium)\/\d+/.test(s)) return { family: "chrome", engine: "chromium" };

    if (/Firefox\/\d+/.test(s)) return { family: "firefox", engine: "gecko" };

    if (/Safari\//.test(s) && !/Chrom(?:e|ium)\//.test(s) && !/OPR\//.test(s) && !/Edg(?:A|iOS)?\//.test(s)) {
      return { family: "safari", engine: "webkit" };
    }

    return { family: "unknown", engine: "unknown" };
  }

  function isIOSLike() {
    const p = navigator.platform || "";
    return /iPhone|iPad|iPod/.test(p) || (p === "MacIntel" && navigator.maxTouchPoints > 1);
  }

  function detectEngine() {
    const gecko =
      typeof InstallTrigger !== "undefined" ||
      ("MozAppearance" in (document.documentElement?.style || {})) ||
      (typeof CSS !== "undefined" && CSS.supports && CSS.supports("-moz-appearance: none"));
    if (gecko) return "gecko";

    const chromiumish =
      !!navigator.userAgentData ||
      (typeof window.chrome === "object" && window.chrome !== null) ||
      (!!navigator.connection && typeof navigator.connection.effectiveType === "string");
    if (chromiumish) return "chromium";

    return "webkit"; // remainder
  }

  function getChromiumActualFamilySync() {
    const uad = navigator.userAgentData;
    if (uad && Array.isArray(uad.brands)) {
      let hasEdge = false, hasOpera = false, hasChrome = false, hasChromium = false;
      for (const b of uad.brands) {
        const brand = String(b.brand || "");
        if (/Microsoft Edge/i.test(brand)) hasEdge = true;
        else if (/Opera/i.test(brand)) hasOpera = true;
        else if (/Google Chrome/i.test(brand)) hasChrome = true;
        else if (/Chromium/i.test(brand)) hasChromium = true;
      }
      if (hasEdge) return "edge";
      if (hasOpera) return "opera";
      if (hasChrome || hasChromium) return "chrome";
    }

    if ("opr" in window) return "opera";

    return "chrome";
  }

  function familiesMatch(claim, actualEngine) {
    if (claim && claim.family === "headlesschrome") return false;

    if (claim.engine !== actualEngine) return false;

    if (actualEngine === "gecko") return claim.family === "firefox";

    if (actualEngine === "webkit") {
      if (isIOSLike()) return ["safari", "chrome", "firefox", "edge", "opera"].includes(claim.family);
      return claim.family === "safari";
    }

    if (actualEngine === "chromium") {
      const actualFam = getChromiumActualFamilySync(); // "chrome" | "edge" | "opera"
      return claim.family === actualFam || (claim.family === "chromium" && actualFam === "chrome");
    }

    return false;
  }

  // ---------- main ----------
  const result = readJson("what-is-my-browser", {});
  const openUrl  = readJson("open-url", "/resources/open.html");
  const hostEl   = document.getElementById("response");

  if (!hostEl) return;

  if (navigator.webdriver === true) {
    fail(hostEl);
    return;
  }

  let claimUA = pickUA(result);
  let claim = claimUA ? parseUAClaim(claimUA) : null;

  if (!claim || claim.engine === "unknown") {
    const fam = typeof result.family === "string" ? result.family.toLowerCase() : "unknown";
    const engine =
      fam === "firefox" ? "gecko" :
      fam === "safari" ? "webkit" :
      (fam === "chrome" || fam === "edge" || fam === "opera" || fam === "chromium") ? "chromium" :
      "unknown";
    claim = { family: fam, engine };
  }

  const actualEngine = detectEngine();
  log("Claim:", claim, "Actual engine:", actualEngine);

  if (!familiesMatch(claim, actualEngine)) {
    fail(hostEl);
    return;
  }

  // Passed -> open
  document.title = "The Ancient Door - Opened";
  fetch(openUrl, { credentials: "same-origin" })
    .then(r => { if (!r.ok) throw new Error("failed to load open content"); return r.text(); })
    .then(html => { hostEl.innerHTML = html; })
    .catch(() => { hostEl.insertAdjacentHTML("beforeend", "<p>Failed to load content.</p>"); });
})();
