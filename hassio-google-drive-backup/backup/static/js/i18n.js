// Browser-side translation helper.
//
// The bootstrap response populates window.I18N (an English-source ->
// localized-text map for the active language), along with window.I18N_LANG
// and window.I18N_DIR. This file is loaded before scripts.js so the rest
// of the front-end code can call _("...") uniformly.

window.I18N = window.I18N || {};

function _(source) {
  if (!source) return source;
  if (Object.prototype.hasOwnProperty.call(window.I18N, source)) {
    return window.I18N[source];
  }
  return source;
}

// Convenience wrapper for messages with positional placeholders ({0}, {1}, ...).
function _f(source) {
  var translated = _(source);
  for (var i = 1; i < arguments.length; i++) {
    translated = translated.split("{" + (i - 1) + "}").join(arguments[i]);
  }
  return translated;
}
