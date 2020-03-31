class Color {
    constructor(r=0, g=0, b=0, a=1) {
      this.r = this._clamp(r);
      this.g = this._clamp(g);
      this.b = this._clamp(b);
      this.a = this._clamp(a, 0, 1);
    }
  
    static black() {
      return new Color(0, 0, 0);
    }
  
    static white() {
      return new Color(255, 255, 255)
    }
  
    static grey() {
      return new Color(128, 128, 128)
    }
  
    static parse(color) {
      let rgb =  $.colpick.hexToRgb(color.substring(1, 7));
      return new Color(rgb['r'], rgb['g'], rgb['b']);
    }
  
    tint(to, amount) {
      amount = this._clamp(amount, 0, 1);
  
      let r_new = this.r + (to.r - this.r) * amount;
      let g_new = this.g + (to.g - this.g) * amount;
      let b_new = this.b + (to.b - this.b) * amount;
      let a_new = this.a + (to.a - this.a) * amount;
      return new Color(r_new, g_new, b_new, a_new);
    }
  
    darken(amount) {
      return this.tint(Color.black(), amount);
    }
  
    lighten(amount) {
      return this.tint(Color.white(), amount);
    }
    
    saturate(change) {
      let Pr = 0.299;
      let Pg = 0.587;
      let Pb = 0.114;
      let P = Math.sqrt(this.r * this.r * Pr + this.g * this.g * Pg + this.b * this.b * Pb);
  
      let R = this._clamp(P + (this.r - P) * change);
      let G = this._clamp(P + (this.g - P) * change);
      let B = this._clamp(P + (this.b - P) * change);
      return new Color(R, G, B, this.a);
    }
  
    _clamp(value, min=0, max=255) {
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
      return "#" + $.colpick.rgbToHex({'r': Math.floor(this.r), 'g': Math.floor(this.g), 'b': Math.floor(this.b)});
    }
  
    textColor() {
      let luma = ((0.299 * this.r) + (0.587 * this.g) + (0.114 * this.b)) / 255;
      return luma > 0.53 ? Color.black() : Color.white();
    }
  
    luminance() {
      let rg = Math.floor(this.r) <= 10 ?  this.r/3294.0 :Math.pow(this.r/269.0 + 0.0513, 2.4);
      let gg = Math.floor(this.g) <= 10 ?  this.g/3294.0 :Math.pow(this.g/269.0 + 0.0513, 2.4);
      let bg = Math.floor(this.b) <= 10 ?  this.b/3294.0 :Math.pow(this.b/269.0 + 0.0513, 2.4);
      return 0.2126 * rg + 0.7152 * gg + 0.0722 * bg;
    }
  
    contrast(other) {
      let big = this.luminance();
      let small = other.luminance();
  
      if (big < small) {
        let temp = big;
        big = small;
        small = temp;
      }
  
      return (big + 0.05) / (small + 0.05);
    }
  
    withAlpha(alpha) {
      return new Color(this.r, this.g, this.b, alpha);
    }
  }
    var scope = ['https://www.googleapis.com/auth/drive.file'];
  
    var pickerApiLoaded = false;
    var oauthToken;
  
    function loadPicker() {
      gapi.load('auth', {'callback': onAuthApiLoad});
      gapi.load('picker', {'callback': onPickerApiLoad});
    }
  
    function onAuthApiLoad() {
      window.gapi.auth.authorize({
        'client_id': clientId,
        'scope': scope,
        'immediate': false
       }, handleAuthResult);
    }
  
    function onPickerApiLoad() {
      pickerApiLoaded = true;
      createPicker();
    }
  
    function handleAuthResult(authResult) {
      if (authResult && !authResult.error) {
        oauthToken = authResult.access_token;
        createPicker();
      }
    }
  
    // Create and render a Picker object for searching images.
    function createPicker() {
      if (pickerApiLoaded && oauthToken) {
        var mydrive = new google.picker.DocsView(google.picker.ViewId.DOCS)
            .setMode(google.picker.DocsViewMode.LIST)
            .setIncludeFolders(true)
            .setSelectFolderEnabled(true)
            .setParent('root')
            .setLabel("My Drive");
        var sharedWithMe = new google.picker.DocsView(google.picker.FOLDERS)
            .setMode(google.picker.DocsViewMode.LIST)
            //.setIncludeFolders(true)
            .setSelectFolderEnabled(true)
            .setOwnedByMe(true)
            .setQuery("*")
            .setLabel("Shared With Me");
        var sharedDrives = new google.picker.DocsView(google.picker.ViewId.DOCS)
            .setEnableDrives(true) 
            .setMode(google.picker.DocsViewMode.LIST) 
            .setIncludeFolders(true)
            .setSelectFolderEnabled(true);
        var recent = new google.picker.DocsView(google.picker.ViewId.RECENTLY_PICKED)
            .setMode(google.picker.DocsViewMode.LIST)
            .setIncludeFolders(true)
            .setSelectFolderEnabled(true);
        var picker = new google.picker.PickerBuilder()
            .disableFeature(google.picker.Feature.NAV_HIDDEN)
            .disableFeature(google.picker.Feature.MINE_ONLY)
            .enableFeature(google.picker.Feature.SUPPORT_DRIVES)
            .setAppId(appId)
            .setOAuthToken(oauthToken)
            .addView(mydrive)
            //.addView(sharedWithMe)
            .addView(sharedDrives)
            .addView(recent)
            .setTitle("Choose a backup folder")
            .setCallback(pickerCallback)
            .build();
         picker.setVisible(true);
      }
   }
  
    function getQueryParams( params) {
      let href = window.location;
      //this expression is to get the query strings
      let reg = new RegExp( '[?&]' + params + '=([^&#]*)', 'i' );
      let queryString = reg.exec(href);
      return queryString ? queryString[1] : null;
    };
  
    // A simple callback implementation.
    function pickerCallback(data) {
      if (data.action == google.picker.Action.PICKED) {
        var message = "";
        if (data.docs.length == 0) {
          message = "No document was selected.  Please try selecting a folder again."
        } else if (data.docs[0].mimeType != "application/vnd.google-apps.folder") {
          // Has to be a folder.  Doesn't make sense otherwise.
          message = "You can only backup snapshots to a folder.  Please select a folder instead."
        }
  
        if (message.length > 0) {
          alert(message);
        } else {
          // Redirect back to the uer's home assistant with the now authorized folder id.
          window.location.href = decodeURIComponent(getQueryParams("returnto")) + "?id=" + data.docs[0].id
        }
      }
    }
  
  function updateColorSelector(target, color) {
    target.html(color.toHex());
    target.css("background-color", color.toCss());
    target.css("color", color.textColor().toCss());
    target.css("border", "2px");
    target.css("border-color", color.textColor().toCss());
    target.css("border-style", 'solid');
  }
  
  function colorSubmit(hsb,hex,rgb,el,bySetColor){
    setStyles();
    $(el).colpickHide();
  }
  
  function setStyles() {
    background = Color.parse($("#background_color").html());
    accent = Color.parse($("#accent_color").html());
    setColors(background, accent);
  }
  
  function revertColors() {
    background = Color.parse(defaults.background_color);
    updateColorSelector($("#background_color"), background);
    accent = Color.parse(defaults.accent_color);
    updateColorSelector($("#accent_color"), accent);
  
    setColors(background, accent);
  }
  
  function setColors(background, accent) {
    let text = background.textColor();
    let accent_text = accent.textColor();
    let link_accent = accent;
    let contrast_threshold = 4.5;
  
    let contrast = background.contrast(accent);
    if (contrast < contrast_threshold) {
      // do some adjustment to make the UI more readable if the contrast is really bad
      let scale = 1 - (contrast - 1)/(contrast_threshold - 1);
      link_accent = link_accent.tint(text, scale * 0.5);
    }
  
    let focus = accent.saturate(1.2);
    let help = text.tint(background, 0.25);
  
    let shadow1 = text.withAlpha(0.14);
    let shadow2 = text.withAlpha(0.12);
    let shadow3 = text.withAlpha(0.2);
    let bgshadow = "0 2px 2px 0 " + shadow1.toCss() + ", 0 3px 1px -2px " + shadow2.toCss() + ", 0 1px 5px 0 " + shadow3.toCss();
  
    let bg_modal = background.tint(text, 0.02);
    let shadow_modal = "box-shadow: 0 24px 38px 3px " + shadow1.toCss() + ", 0 9px 46px 8px " + shadow2.toCss() + ", 0 11px 15px -7px " + shadow3.toCss();
  
    setRule("html", {
      'background-color': background.toCss(),
      'color': text.toCss()
    });
  
    setRule("label", {
      'color': text.toCss()
    });
  
    setRule("a", {
      'color': link_accent.toCss()
    });
  
    setRule("input", {
      'color': text.toCss()
    });
  
    setRule(".helper-text", {
      'color': help.toCss()
    });
  
    setRule(".ha-blue", {
      'background-color': accent.toCss(),
      'color': accent_text.toCss()
    });
  
    setRule("nav .brand-logo", {
      'color': accent_text.toCss()
    })
  
    setRule("nav ul a", {
      'color': accent_text.toCss()
    })
  
    setRule(".accent-title", {
      'color': accent_text.toCss()
    })
  
    setRule("footer a:link", {
      'text-decoration': 'underline',
      'color': accent_text.textColor().tint(accent_text, 0.95).toCss()
    });
  
    setRule(".accent-text", {
      'color': accent_text.textColor().tint(accent_text, 0.95).toCss()
    })
  
    setRule(".btn", {
      'background-color': accent.toCss()
    });
  
    setRule(".btn:hover, .btn-large:hover, .btn-small:hover", {
      'background-color': accent.toCss(),
      'color': accent_text.toCss()
    });
  
    setRule(".btn:focus, .btn-large:focus, .btn-small:focus, .btn-floating:focus", {
      'background-color': focus.toCss(),
    });
  
    setRule(".modal .modal-footer .btn, .modal .modal-footer .btn-large, .modal .modal-footer .btn-small, .modal .modal-footer .btn-flat",  {
      'margin': '6px 0',
      'background-color': accent.toCss(),
      'color': accent_text.toCss()
    });
  
    setRule(".dropdown-content", {
      'background-color': background.toCss(),
      'box-shadow': bgshadow,
      'webkit-box-shadow': bgshadow,
    });
  
    setRule(".dropdown-content li > a", {
      'color': text.tint(background, 0.5).toCss()
    });
  
    setRule(".modal", {
      'background-color': bg_modal.toCss(),
      'box-shadow': shadow_modal
    });
  
    setRule(".modal .modal-footer", {
      'background-color':  bg_modal.toCss()
    });
  
    setRule(".modal.modal-fixed-footer .modal-footer", {
      'border-top': '1px solid ' + text.withAlpha(0.1).toCss()
    });
  
    setRule(".modal-overlay", {
      'background': text.toCss()
    });
  
    setRule("[type=\"checkbox\"].filled-in:checked + span:not(.lever)::before", {
      'border-right': '2px solid ' + text.toCss(),
      'border-bottom': '2px solid ' + text.toCss()
    });
  
    setRule("[type=\"checkbox\"].filled-in:checked + span:not(.lever)::after", {
      'border': '2px solid ' + text.toCss(),
      'background-color': accent.darken(0.2).saturate(1.2).toCss()
    });
  
    setRule(".input-field .prefix.active", {
      'color': accent.toCss()
    });
  
    setRule(".input-field > label", {
      'color': help.toCss()
    });
  
    setRule(".input-field .helper-text", {
      'color': help.toCss()
    });
  
    setRule("input:not([type]):focus:not([readonly]) + label, input[type=\"text\"]:not(.browser-default):focus:not([readonly]) + label, input[type=\"password\"]:not(.browser-default):focus:not([readonly]) + label, input[type=\"email\"]:not(.browser-default):focus:not([readonly]) + label, input[type=\"url\"]:not(.browser-default):focus:not([readonly]) + label, input[type=\"time\"]:not(.browser-default):focus:not([readonly]) + label, input[type=\"date\"]:not(.browser-default):focus:not([readonly]) + label, input[type=\"datetime\"]:not(.browser-default):focus:not([readonly]) + label, input[type=\"datetime-local\"]:not(.browser-default):focus:not([readonly]) + label, input[type=\"tel\"]:not(.browser-default):focus:not([readonly]) + label, input[type=\"number\"]:not(.browser-default):focus:not([readonly]) + label, input[type=\"search\"]:not(.browser-default):focus:not([readonly]) + label, textarea.materialize-textarea:focus:not([readonly]) + label", {
      'color': text.toCss()
    });
  
    setRule("input.valid:not([type]), input.valid:not([type]):focus, input[type=\"text\"].valid:not(.browser-default), input[type=\"text\"].valid:not(.browser-default):focus, input[type=\"password\"].valid:not(.browser-default), input[type=\"password\"].valid:not(.browser-default):focus, input[type=\"email\"].valid:not(.browser-default), input[type=\"email\"].valid:not(.browser-default):focus, input[type=\"url\"].valid:not(.browser-default), input[type=\"url\"].valid:not(.browser-default):focus, input[type=\"time\"].valid:not(.browser-default), input[type=\"time\"].valid:not(.browser-default):focus, input[type=\"date\"].valid:not(.browser-default), input[type=\"date\"].valid:not(.browser-default):focus, input[type=\"datetime\"].valid:not(.browser-default), input[type=\"datetime\"].valid:not(.browser-default):focus, input[type=\"datetime-local\"].valid:not(.browser-default), input[type=\"datetime-local\"].valid:not(.browser-default):focus, input[type=\"tel\"].valid:not(.browser-default), input[type=\"tel\"].valid:not(.browser-default):focus, input[type=\"number\"].valid:not(.browser-default), input[type=\"number\"].valid:not(.browser-default):focus, input[type=\"search\"].valid:not(.browser-default), input[type=\"search\"].valid:not(.browser-default):focus, textarea.materialize-textarea.valid, textarea.materialize-textarea.valid:focus, .select-wrapper.valid > input.select-dropdown", {
      'border-bottom': '1px solid ' + accent.toCss(),
      ' -webkit-box-shadow':' 0 1px 0 0 ' + accent.toCss(),
      'box-shadow': '0 1px 0 0 ' + accent.toCss()
    });
  
    setRule("input:not([type]):focus:not([readonly]), input[type=\"text\"]:not(.browser-default):focus:not([readonly]), input[type=\"password\"]:not(.browser-default):focus:not([readonly]), input[type=\"email\"]:not(.browser-default):focus:not([readonly]), input[type=\"url\"]:not(.browser-default):focus:not([readonly]), input[type=\"time\"]:not(.browser-default):focus:not([readonly]), input[type=\"date\"]:not(.browser-default):focus:not([readonly]), input[type=\"datetime\"]:not(.browser-default):focus:not([readonly]), input[type=\"datetime-local\"]:not(.browser-default):focus:not([readonly]), input[type=\"tel\"]:not(.browser-default):focus:not([readonly]), input[type=\"number\"]:not(.browser-default):focus:not([readonly]), input[type=\"search\"]:not(.browser-default):focus:not([readonly]), textarea.materialize-textarea:focus:not([readonly])", {
      'border-bottom': '1px solid ' + accent.toCss(),
      '-webkit-box-shadow': '0 1px 0 0 ' + accent.toCss(),
      'box-shadow': '0 1px 0 0 ' + accent.toCss()
    });
  
    setRule(".card", {
      'background-color': background.toCss(),
      'box-shadow': "0 2px 2px 0 " + shadow1.toCss() + ", 0 3px 1px -2px " + shadow2.toCss() + ", 0 1px 5px 0 " + shadow3.toCss()
    });
  
    setRule("nav a",  {
      'color': accent_text.toCss()
    });
  
    setRule(".btn, .btn-large, .btn-small",  {
      'color': accent_text.toCss()
    });
  }
  
  // Modifying style sheets directly probably isn't best practices, but damn does it work well.
  function setRule(selector, rules) {
    let ruleset = document.getElementById("theme").sheet.cssRules;
    for (var i = 0; i < ruleset.length; i++){
      let cssRule = ruleset[i];
      if (cssRule.selectorText == selector) {
        for (rule in rules) {
          cssRule.style.setProperty(rule, rules[rule]);
        }
        return;
      }
    }
  
    console.log("No rule with selector " + selector);
  }
  
  function doColors() {
    setColors(Color.parse(decodeURIComponent(getQueryParams("bg"))), Color.parse(decodeURIComponent(getQueryParams("ac"))));
  }
  
  $(document).ready(function() {
    doColors();
  });
  