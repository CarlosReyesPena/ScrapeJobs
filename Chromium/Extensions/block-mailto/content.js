document.addEventListener('click', function(event) {
  if (event.target.tagName === 'A' && event.target.href.startsWith('mailto:')) {
    event.preventDefault();
    console.log('Blocked mailto:', event.target.href);
  }
}, true);

document.addEventListener('click', function(event) {
  let element = event.target;
  while (element) {
    if (element.tagName === 'A' && element.href && element.href.startsWith('mailto:')) {
      event.preventDefault();
      console.log('Blocked mailto:', element.href);
      return;
    }
    element = element.parentElement;
  }
}, true);

// Intercepter les requêtes mailto initiées par JavaScript
const originalOpen = XMLHttpRequest.prototype.open;
XMLHttpRequest.prototype.open = function(method, url) {
  if (url.startsWith('mailto:')) {
    console.log('Blocked mailto request via XMLHttpRequest:', url);
    return;
  }
  return originalOpen.apply(this, arguments);
};

const originalFetch = window.fetch;
window.fetch = function() {
  const url = arguments[0];
  if (typeof url === 'string' && url.startsWith('mailto:')) {
    console.log('Blocked mailto request via fetch:', url);
    return Promise.reject(new Error('Blocked mailto request'));
  }
  return originalFetch.apply(this, arguments);
};
