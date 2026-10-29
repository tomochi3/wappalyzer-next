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
  try {
    const [{ result: injected } = {}] = await chrome.scripting.executeScript({
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

    if (!injected) {
      await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        files: ['js/content.js'],
      })
    }
  } catch (error) {
    // e.g. the Chrome Web Store or other pages extensions may not access
    return
  }

  // Response headers: one request to the page, made now, without cookies
  try {
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
  } catch (error) {
    // headers are optional; the page content is analysed regardless
  }

  // the content script reports in stages (about 1 s, then a 5 s second pass)
  for (const delay of [1500, 2500, 4000]) {
    await new Promise((resolve) => setTimeout(resolve, delay))
    await refresh()
  }
})()
