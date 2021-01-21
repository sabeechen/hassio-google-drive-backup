const themeStyleContainer = document.getElementById("theme");

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

  shift(amount) {
    return this.luminance() >= 0.5 ? this.darken(amount) : this.lighten(amount);
  }

  saturate(change) {
    const Pr = 0.299;
    const Pg = 0.587;
    const Pb = 0.114;
    const P = Math.sqrt(this.r * this.r * Pr + this.g * this.g * Pg + this.b * this.b * Pb);

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
    return "rgba(" + Math.floor(this.r) + "," + Math.floor(this.g) + "," + Math.floor(this.b) + "," + this.a + ")";
  }

  toHex() {
    const componentToHex = (c) => {
      var hex = c.toString(16);
      return hex.length == 1 ? "0" + hex : hex;
    };

    return (
      "#" + componentToHex(Math.floor(this.r)) + componentToHex(Math.floor(this.g)) + componentToHex(Math.floor(this.b))
    );
  }

  textColor() {
    const luma = (0.299 * this.r + 0.587 * this.g + 0.114 * this.b) / 255;
    return luma > 0.53 ? Color.black() : Color.white();
  }

  luminance() {
    const rg = Math.floor(this.r) <= 10 ? this.r / 3294.0 : Math.pow(this.r / 269.0 + 0.0513, 2.4);
    const gg = Math.floor(this.g) <= 10 ? this.g / 3294.0 : Math.pow(this.g / 269.0 + 0.0513, 2.4);
    const bg = Math.floor(this.b) <= 10 ? this.b / 3294.0 : Math.pow(this.b / 269.0 + 0.0513, 2.4);
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

  const contrastThreshold = 4.5;
  const contrast = background.contrast(accent);
  let linkAccent = accent;
  if (contrast < contrastThreshold) {
    // do some adjustment to make the UI more readable if the contrast is really bad
    const scale = 1 - (contrast - 1) / (contrastThreshold - 1);
    linkAccent = linkAccent.tint(text, scale * 0.5);
  }

  const styleSheet = {
    ":root": {
      // Cls colors
      "--cls-color": text.toCss(),
      "--cls-sec-color": text.toCss(),
      "--cls-size": "2rem",
      "--cls-margin": "1rem",
      "--cls-speed": "4s",
      // Texts & icons colors
      "--helper-text-color": text.tint(background, 0.25).toCss(),
      "--text-primary-color": text.shift(0.13).toCss(),
      "--text-secondary-color": text.shift(0.26).toCss(),
      "--divider-color": text.withAlpha(0.12).toCss(),
      "--icon-color": text.shift(0.13).withAlpha(0.6).toCss(),
      // Accent colors
      "--accent-color": accent.toCss(),
      "--accent-text-color": accent.textColor().toCss(),
      "--accent-focus-color": accent.saturate(1.2).toCss(),
      "--accent-hover-color": accent.saturate(1.8).toCss(),
      "--accent-link-color": linkAccent.toCss(),
      "--accent-ripple": linkAccent.withAlpha(0.2).toCss(),
      // Background colors
      "--background-color": background.toCss(),
      "--background-sidenav-color": background.shift(0.03).toCss(),
      "--background-hover": background.shift(0.065),
      "--background-modal-color": background.tint(text, 0.02).toCss(),
      "--background-primary-color": background.shift(0.02).toCss(),
    },
  };

  const properties = Object.keys(styleSheet).map((selector) => {
    const selectorProperties = Object.keys(styleSheet[selector]).map(
      (property) => `    ${property}: ${styleSheet[selector][property]};`,
    );

    return `${selector} {\n${selectorProperties.join("\n")}\n}`;
  });

  themeStyleContainer.innerHTML = properties.join("\n");
}

setColors(
  Color.parse(themeStyleContainer.dataset.backgroundColor),
  Color.parse(themeStyleContainer.dataset.accentColor),
);
