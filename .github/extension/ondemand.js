/* globals chrome, Popup */

// On-demand mode, added by wappalyzer-next's .github/update.py.
//
// The Chrome build of the extension has no content scripts, no webRequest
// listeners and no host permissions, so it reads nothing while you browse.
// Opening this popup grants activeTab for the current tab only; this script
// then analyses that tab and refreshes the popup as results come in.
//
// The command-line scanner restores the automatic mode (content scripts and
// host permissions) when it loads the extension, so this script does nothing
// there.
;(async () => {
  if (chrome.runtime.getManifest().content_scripts) {
    return
  }

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })

  if (!tab || !/^https?:/i.test(tab.url || '')) {
    return
  }

  const refresh = () =>
    Popup.driver('getDetections')
      .then(Popup.onGetDetections.bind(Popup))
      .catch(() => {})

  // Page content, scripts, cookies and JavaScript globals: run the regular
  // content script in the tab, or re-run it if this popup was opened before
  let injected

  try {
    ;[{ result: injected } = {}] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => {
        // eslint-disable-next-line no-undef
        if (typeof Content === 'undefined') {
          return false
        }

        // eslint-disable-next-line no-undef
        Content.init()

        return true
      },
    })
  } catch (error) {
    // e.g. the Chrome Web Store or other pages extensions may not access
    return
  }

  // resolves only once the content script has finished (after its 5 s
  // second pass), so it runs alongside the other checks
  const analyseContent = async () => {
    if (!injected) {
      await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        files: ['js/content.js'],
      })
    }
  }

  // Response headers: one request to the page, made now, without cookies
  const analyseHeaders = async () => {
    let response = await fetch(tab.url, {
      method: 'HEAD',
      credentials: 'omit',
      cache: 'no-store',
    })

    if (response.status === 405 || response.status === 501) {
      response = await fetch(tab.url, { credentials: 'omit', cache: 'no-store' })
    }

    const responseHeaders = []

    response.headers.forEach((value, name) => responseHeaders.push({ name, value }))

    await Popup.driver('onWebRequestComplete', [
      { url: tab.url, tabId: tab.id, responseHeaders },
    ])
  }

  // Script contents and request destinations: the automatic mode reads
  // these from network events while the page loads. Here the page lists the
  // resources it has loaded so far, and the same checks run on those.
  const analyseResources = async () => {
    const [{ result: resources } = {}] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => {
        const entries = performance.getEntriesByType('resource')
        const scripts = new Set(
          [...document.scripts].map((script) => script.src).filter(Boolean)
        )

        entries
          .filter(
            ({ initiatorType, name }) =>
              initiatorType === 'script' ||
              (initiatorType === 'link' && /\.m?js(?:[?#]|$)/.test(name))
          )
          .forEach(({ name }) => scripts.add(name))

        const requests = entries
          .filter(({ initiatorType }) =>
            ['xmlhttprequest', 'fetch', 'beacon'].includes(initiatorType)
          )
          .map(({ name }) => name)

        return { scripts: [...scripts], requests: [...new Set(requests)] }
      },
    })

    const origin = new URL(tab.url).origin
    const request = (url) => ({
      url,
      tabId: tab.id,
      frameId: 0,
      initiator: tab.url,
    })

    // the page's own bundles first: activeTab lets the extension read those
    const scripts = (resources?.scripts || [])
      .filter((url) => /^https?:/i.test(url))
      .sort(
        (a, b) =>
          (b.startsWith(origin) ? 1 : 0) - (a.startsWith(origin) ? 1 : 0)
      )

    await Promise.all([
      ...scripts.map((url) =>
        Popup.driver('onScriptRequestComplete', [request(url)])
      ),
      ...(resources?.requests || []).map((url) =>
        Popup.driver('onXhrRequestComplete', [request(url)])
      ),
    ])
  }

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
  const started = Date.now()
  let done = false

  Promise.allSettled([analyseContent(), analyseHeaders(), analyseResources()])
    .then(() => sleep(1500)) // request destinations are reported after 1 s
    .then(() => {
      done = true

      return refresh()
    })

  // show results as they arrive: the content script reports after about
  // 1 s and again after 5 s, and large bundles take a few seconds to scan
  while (Date.now() - started < 30000) {
    await sleep(1500)
    await refresh()

    if (done && Date.now() - started >= 8000) {
      break
    }
  }
})()
