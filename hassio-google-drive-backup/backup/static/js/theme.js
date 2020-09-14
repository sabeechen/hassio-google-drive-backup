const themeStyleContainer = document.getElementById('theme');

class Color {
  constructor(r = 0, g = 0, b = 0, a = 1) {
    this.r = this._clamp(r);
    this.g = this._clamp(g);
    this.b = this._clamp(b);
    this.a = this._clamp(a, 0, 1);
  }

  static black() {
    return new Color(0, 0, 0);
  }

  static white() {
    return new Color(255, 255, 255);
  }

  static grey() {
    return new Color(128, 128, 128);
  }

  static hexToRgb(hex) {
    const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
    return result
      ? {
          r: parseInt(result[1], 16),
          g: parseInt(result[2], 16),
          b: parseInt(result[3], 16),
        }
      : null;
  }

  static parse(color) {
    const rgb = this.hexToRgb(color);
    return new Color(rgb.r, rgb.g, rgb.b);
  }

  tint(to, amount) {
    amount = this._clamp(amount, 0, 1);

    const r_new = this.r + (to.r - this.r) * amount;
    const g_new = this.g + (to.g - this.g) * amount;
    const b_new = this.b + (to.b - this.b) * amount;
    const a_new = this.a + (to.a - this.a) * amount;
    return new Color(r_new, g_new, b_new, a_new);
  }

  darken(amount) {
    return this.tint(Color.black(), amount);
  }

  lighten(amount) {
    return this.tint(Color.white(), amount);
  }

  saturate(change) {
    const Pr = 0.299;
    const Pg = 0.587;
    const Pb = 0.114;
    const P = Math.sqrt(
      this.r * this.r * Pr + this.g * this.g * Pg + this.b * this.b * Pb
    );

    const R = this._clamp(P + (this.r - P) * change);
    const G = this._clamp(P + (this.g - P) * change);
    const B = this._clamp(P + (this.b - P) * change);
    return new Color(R, G, B, this.a);
  }

  _clamp(value, min = 0, max = 255) {
    if (value > max) {
      return max;
    }
    if (value < min) {
      return min;
    }
    return value;
  }

  toCss() {
    return (
      'rgba(' +
      Math.floor(this.r) +
      ',' +
      Math.floor(this.g) +
      ',' +
      Math.floor(this.b) +
      ',' +
      this.a +
      ')'
    );
  }

  toHex() {
    const componentToHex = (c) => {
      var hex = c.toString(16);
      return hex.length == 1 ? '0' + hex : hex;
    };

    return (
      '#' +
      componentToHex(Math.floor(this.r)) +
      componentToHex(Math.floor(this.g)) +
      componentToHex(Math.floor(this.b))
    );
  }

  textColor() {
    const luma = (0.299 * this.r + 0.587 * this.g + 0.114 * this.b) / 255;
    return luma > 0.53 ? Color.black() : Color.white();
  }

  luminance() {
    const rg =
      Math.floor(this.r) <= 10
        ? this.r / 3294.0
        : Math.pow(this.r / 269.0 + 0.0513, 2.4);
    const gg =
      Math.floor(this.g) <= 10
        ? this.g / 3294.0
        : Math.pow(this.g / 269.0 + 0.0513, 2.4);
    const bg =
      Math.floor(this.b) <= 10
        ? this.b / 3294.0
        : Math.pow(this.b / 269.0 + 0.0513, 2.4);
    return 0.2126 * rg + 0.7152 * gg + 0.0722 * bg;
  }

  contrast(other) {
    let big = this.luminance();
    let small = other.luminance();

    if (big < small) {
      const temp = big;
      big = small;
      small = temp;
    }

    return (big + 0.05) / (small + 0.05);
  }

  withAlpha(alpha) {
    return new Color(this.r, this.g, this.b, alpha);
  }
}

function setColors(background, accent) {
  const text = background.textColor();
  const accentText = accent.textColor();
  const contrastThreshold = 4.5;
  const contrast = background.contrast(accent);

  let linkAccent = accent;
  if (contrast < contrastThreshold) {
    // do some adjustment to make the UI more readable if the contrast is really bad
    const scale = 1 - (contrast - 1) / (contrastThreshold - 1);
    linkAccent = linkAccent.tint(text, scale * 0.5);
  }

  const focus = accent.saturate(1.2);
  const help = text.tint(background, 0.25);

  const shadow1 = text.withAlpha(0.14);
  const shadow2 = text.withAlpha(0.12);
  const shadow3 = text.withAlpha(0.2);
  const shadowBmc = background.withAlpha(0.2);
  const bgShadow = `0 2px 2px 0 ${shadow1.toCss()}, 0 3px 1px -2px ${shadow2.toCss()}, 0 1px 5px 0 ${shadow3.toCss()}`;
  const bgModal = background.tint(text, 0.02);

  const styleSheet = {
    'html': {
      'background-color': background.toCss(),
      'color': text.toCss(),
    },
    'label': {
      'color': text.toCss(),
    },
    'a': {
      'color': linkAccent.toCss(),
    },
    'input': {
      'color': text.toCss(),
    },
    '.helper-text': {
      'color': help.toCss(),
    },
    '.ha-blue': {
      'background-color': accent.toCss(),
      'color': accentText.toCss(),
    },
    'nav .brand-logo': {
      'color': accentText.toCss(),
    },
    'nav ul a': {
      'color': accentText.toCss(),
    },
    '.accent-title': {
      'color': accentText.toCss(),
    },
    'footer a:link': {
      'text-decoration': 'underline',
      'color': accentText.textColor().tint(accentText, 0.95).toCss(),
    },
    '.accent-text': {
      'color': accentText.textColor().tint(accentText, 0.95).toCss(),
    },
    '.btn': {
      'background-color': accent.toCss(),
    },
    '.btn:hover, .btn-large:hover, .btn-small:hover': {
      'background-color': accent.toCss(),
      'color': accentText.toCss(),
    },
    '.btn:focus, .btn-large:focus, .btn-small:focus, .btn-floating:focus': {
      'background-color': focus.toCss(),
    },
    '.modal .modal-footer .btn, .modal .modal-footer .btn-large, .modal .modal-footer .btn-small, .modal .modal-footer .btn-flat': {
      'margin': '6px 0',
      'background-color': accent.toCss(),
      'color': accentText.toCss(),
    },
    '.dropdown-content': {
      'background-color': background.toCss(),
      'box-shadow': bgShadow,
      'webkit-box-shadow': bgShadow,
    },
    '.dropdown-content li > a': {
      'color': text.tint(background, 0.5).toCss(),
    },
    '.highlight-border': {
      'border-color': accent.toCss(),
      'border-width': '1px',
      'border-style': 'solid',
    },
    '.modal': {
      'background-color': bgModal.toCss(),
      'box-shadow': `box-shadow: 0 24px 38px 3px ${shadow1.toCss()}, 0 9px 46px 8px ${shadow2.toCss()}, 0 11px 15px -7px ${shadow3.toCss()}`,
    },
    '.modal .modal-footer': {
      'background-color': bgModal.toCss(),
    },
    '.modal.modal-fixed-footer .modal-footer': {
      'border-top': `1px solid ${text.withAlpha(0.1).toCss()}`,
    },
    '[type="checkbox"].filled-in:checked + span:not(.lever)::before': {
      'border-right': `2px solid ${text.toCss()}`,
      'border-bottom': `2px solid ${text.toCss()}`,
    },
    '[type="checkbox"].filled-in:checked + span:not(.lever)::after': {
      'border': `2px solid ${text.toCss()}`,
      'background-color': accent.darken(0.2).saturate(1.2).toCss(),
    },
    '.input-field .prefix.active': {
      'color': accent.toCss(),
    },
    '.input-field > label': {
      'color': help.toCss(),
    },
    '.input-field .helper-text': {
      'color': help.toCss(),
    },
    'input:not([type]):focus:not([readonly]) + label, input[type="text"]:not(.browser-default):focus:not([readonly]) + label, input[type="password"]:not(.browser-default):focus:not([readonly]) + label, input[type="email"]:not(.browser-default):focus:not([readonly]) + label, input[type="url"]:not(.browser-default):focus:not([readonly]) + label, input[type="time"]:not(.browser-default):focus:not([readonly]) + label, input[type="date"]:not(.browser-default):focus:not([readonly]) + label, input[type="datetime"]:not(.browser-default):focus:not([readonly]) + label, input[type="datetime-local"]:not(.browser-default):focus:not([readonly]) + label, input[type="tel"]:not(.browser-default):focus:not([readonly]) + label, input[type="number"]:not(.browser-default):focus:not([readonly]) + label, input[type="search"]:not(.browser-default):focus:not([readonly]) + label, textarea.materialize-textarea:focus:not([readonly]) + label': {
      'color': text.toCss(),
    },
    'input.valid:not([type]), input.valid:not([type]):focus, input[type="text"].valid:not(.browser-default), input[type="text"].valid:not(.browser-default):focus, input[type="password"].valid:not(.browser-default), input[type="password"].valid:not(.browser-default):focus, input[type="email"].valid:not(.browser-default), input[type="email"].valid:not(.browser-default):focus, input[type="url"].valid:not(.browser-default), input[type="url"].valid:not(.browser-default):focus, input[type="time"].valid:not(.browser-default), input[type="time"].valid:not(.browser-default):focus, input[type="date"].valid:not(.browser-default), input[type="date"].valid:not(.browser-default):focus, input[type="datetime"].valid:not(.browser-default), input[type="datetime"].valid:not(.browser-default):focus, input[type="datetime-local"].valid:not(.browser-default), input[type="datetime-local"].valid:not(.browser-default):focus, input[type="tel"].valid:not(.browser-default), input[type="tel"].valid:not(.browser-default):focus, input[type="number"].valid:not(.browser-default), input[type="number"].valid:not(.browser-default):focus, input[type="search"].valid:not(.browser-default), input[type="search"].valid:not(.browser-default):focus, textarea.materialize-textarea.valid, textarea.materialize-textarea.valid:focus, .select-wrapper.valid > input.select-dropdown': {
      'border-bottom': `1px solid ${accent.toCss()}`,
      '-webkit-box-shadow': ` 0 1px 0 0 ${accent.toCss()}`,
      'box-shadow': `0 1px 0 0 ${accent.toCss()}`,
    },
    'input:not([type]):focus:not([readonly]), input[type="text"]:not(.browser-default):focus:not([readonly]), input[type="password"]:not(.browser-default):focus:not([readonly]), input[type="email"]:not(.browser-default):focus:not([readonly]), input[type="url"]:not(.browser-default):focus:not([readonly]), input[type="time"]:not(.browser-default):focus:not([readonly]), input[type="date"]:not(.browser-default):focus:not([readonly]), input[type="datetime"]:not(.browser-default):focus:not([readonly]), input[type="datetime-local"]:not(.browser-default):focus:not([readonly]), input[type="tel"]:not(.browser-default):focus:not([readonly]), input[type="number"]:not(.browser-default):focus:not([readonly]), input[type="search"]:not(.browser-default):focus:not([readonly]), textarea.materialize-textarea:focus:not([readonly])': {
      'border-bottom': `1px solid ${accent.toCss()}`,
      '-webkit-box-shadow': `0 1px 0 0 ${accent.toCss()}`,
      'box-shadow': `0 1px 0 0 ${accent.toCss()}`,
    },
    '.card': {
      'background-color': background.toCss(),
      'box-shadow': `0 2px 2px 0 ${shadow1.toCss()}, 0 3px 1px -2px ${shadow2.toCss()}, 0 1px 5px 0 ${shadow3.toCss()}`,
    },
    'nav a': {
      'color': accentText.toCss(),
    },
    '.btn, .btn-large, .btn-small': {
      'color': accentText.toCss(),
    },
    '.bmc-button': {
      'line-height': '15px',
      'height': '25px',
      'text-decoration': 'none',
      'display': 'inline-flex',
      'background-color': background.toCss(),
      'border-radius': '3px',
      'border': '1px solid transparent',
      'padding': '3px 2px 3px 2px',
      'constter-spacing': '0.6px',
      'box-shadow': `0px 1px 2px ${shadowBmc.toCss()}`,
      '-webkit-box-shadow': `0px 1px 2px 2px ${shadowBmc.toCss()}`,
      'margin': '0 auto',
      'font-family': "'Cookie', cursive",
      '-webkit-box-sizing': 'border-box',
      'box-sizing': 'border-box',
      '-o-transition': '0.3s all linear',
      '-webkit-transition': '0.3s all linear',
      '-moz-transition': '0.3s all linear',
      '-ms-transition': '0.3s all linear',
      'transition': '0.3s all linear',
      'font-size': '17px',
    },
    '.bmc-button span': {
      'color': text.toCss(),
    },
    ':root': {
      '--cls-color': text.toCss(),
      '--cls-sec-color': text.toCss(),
      '--cls-size': '2rem',
      '--cls-margin': '1rem',
      '--cls-speed': '4s',
    }
  };

  const properties = Object.keys(styleSheet).map((selector) => {
    const selectorProperties = Object.keys(styleSheet[selector]).map(
      (property) => `    ${property}: ${styleSheet[selector][property]};`
    );

    return `${selector} {\n${selectorProperties.join('\n')}\n}`;
  });

  themeStyleContainer.innerHTML = properties.join('\n');
}

setColors(
  Color.parse(themeStyleContainer.dataset.backgroundColor),
  Color.parse(themeStyleContainer.dataset.accentColor)
);
