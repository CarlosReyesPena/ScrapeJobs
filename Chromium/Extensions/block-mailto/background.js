chrome.webRequest.onBeforeRequest.addListener(
  function(details) {
    if (details.url.startsWith("mailto:")) {
      console.log("Blocked mailto request: ", details.url);
      return { cancel: true };
    }
  },
  { urls: ["<all_urls>"] },
  ["blocking"]
);
