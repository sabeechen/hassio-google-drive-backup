background_selected = [255, 255, 255];
accent_selected = [0, 0, 0];

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

all_folder_slugs = ['ssl', "addons/local", "homeassistant", "share"];
settingsChanged = false;
name_keys = {}
function idToSlug(id) {
  if (id == "folder_addons") {
    return "addons/local";
  } else if (id == "folder_homeassistant") {
    return "homeassistant";
  } else if (id == 'folder_share') {
    return "share";
  } else if (id == "folder_ssl") {
    return "ssl";
  } else {
    return id;
  }
}

function exampleSnapshotName(snapshot_type, template) {
  if (template.length == 0) {
    template = last_data.snapshot_name_template;
  }
  for (key in name_keys) {
    template = template.replace(key, name_keys[key]);
  }
  return template;
}

function showPallette(element) {
  let target = $(element);
  target.colpick({
    'layout': 'rgbhex',
    'color': target.html(),
    'onSubmit': colorSubmit,
    'onChange': function(hsb,hex,rgb,el,bySetColor){
      settingsChanged = true;
      let color = new Color(rgb['r'], rgb['g'], rgb['b']);
      updateColorSelector(target, color);
      setStyles();
    }
  });
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

  setRule(".bmc-button",  {
    'padding': '3px 5px 3px 5px !important',
    'line-height': '25px !important',
    'height': '35px !important',
    'min-width': '160px !important',
    'text-decoration': 'none !important',
    'display': 'inline-flex !important',
    'color': text.toCss(),
    'background-color': background.toCss(),
    'border-radius': '3px !important',
    'border': '1px solid transparent !important',
    'padding': '3px 5px 3px 5px !important',
    'font-size': '7px !important',
    'letter-spacing': '0.6px !important',
    'box-shadow': '0px 1px 2px rgba(190, 190, 190, 0.5) !important',
    '-webkit-box-shadow': '0px 1px 2px 2px rgba(190, 190, 190, 0.5) !important',
    'margin': '0 auto !important',
    'font-family': "'Cookie', cursive !important",
    '-webkit-box-sizing': 'border-box !important',
    'box-sizing': 'border-box !important',
    '-o-transition': '0.3s all linear !important',
    '-webkit-transition': '0.3s all linear !important',
    '-moz-transition': '0.3s all linear !important',
    '-ms-transition': '0.3s all linear !important',
    'transition': '0.3s all linear !important'
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

function snapshotNameExample() {
  $("#snapshot_example").html(exampleSnapshotName("Full", $("#snapshot_name").val()));
}

function snapshotNameOneOffExample() {
  $("#snapshot_name_example_one_off").html(exampleSnapshotName("Full", $("#snapshot_name_one_off").val()));
}

function checkForSecret() {
  var password = $("#snapshot_password");
  var password2 = $("#snapshot_password_reenter");
  var block = $("#password_renter_block");
  var new_password = password.val();
  var old_password = password.data('old_password');
  if (password.val().startsWith("!secret ")) {
    password.attr('type', 'text');
    block.fadeOut();
    return true;
  } else {
    password.attr('type', 'password');
    if (new_password.length > 0 && old_password != new_password) {
      block.fadeIn();
      if (new_password == password2.val()) {
        password2.removeClass("invalid");
        return true;
      } else {
        password2.addClass("invalid");
        return false;
      }
    } else {
      block.fadeOut();
      return true;
    }
  }
}

function slugToId(id) {
  if (id == "addons/local") {
    return "folder_addons";
  } else if (id == "homeassistant") {
    return "folder_homeassistant";
  } else if (id == 'share') {
    return "folder_share";
  } else if (id == "ssl") {
    return "folder_ssl";
  } else {
    return id;
  }
}


$(document).ready(function () {
  // handle "escape" when settings dialog is presented
  $(document).keyup(function (e) {
    if (e.keyCode === 27) { // 27==escape
      if (M.Modal.getInstance(document.querySelector('#settings_modal')).isOpen) {
        handleCloseSettings();
      }
    }
  });

  var settingsDialog = $("#settings_modal");
  $('#settings_modal :input').change(function () {
    settingsChanged = true;
  });
});

function handleCloseSettings() {
  // determine is the settings hanve changed.
  if (settingsChanged) {
    if (confirm("Discard changes?")) {
      background = Color.parse(config.background_color);
      accent = Color.parse(config.accent_color);
      setColors(background, accent);
      M.Modal.getInstance(document.getElementById("settings_modal")).close();
    }
  } else {
    background = Color.parse(config.background_color);
    accent = Color.parse(config.accent_color);
    setColors(background, accent);
    M.Modal.getInstance(document.getElementById("settings_modal")).close();
  }
}


function loadSettings() {
  var jqxhr = $.get("getconfig",
    function (data) {
      config_data = data
      name_keys = data.name_keys;
      config = data.config;
      addons = data.addons;
      defaults = data.defaults
      for (key in config) {
        if (config.hasOwnProperty(key)) {
          setInputValue(key, config[key]);
        }
      }

      setInputValue("generational_enabled",
        config.generational_days > 0 || config.generational_weeks > 0 || config.generational_months > 0 || config.generational_years > 0);

      // Set the state of excluded folders.
      var excluded_folders = [];
      if (config.hasOwnProperty('exclude_folders') && config.exclude_folders.length > 0) {
        excluded_folders = config.exclude_folders.split(",");
      }
      for (var i = 0; i < all_folder_slugs.length; i++) {
        setInputValue(slugToId(all_folder_slugs[i]), !excluded_folders.includes(all_folder_slugs[i]));
      }

      var exclude_addons = [];
      if (config.hasOwnProperty('exclude_addons') && config.exclude_addons.length > 0) {
        exclude_addons = config.exclude_addons.split(",");
      }

      setInputValue("partial_snapshots", excluded_folders.length > 0 || exclude_addons.length > 0);

      // Set the state of excluded addons.
      $("#settings_addons").html("");
      for (addon in addons) {
        addon = addons[addon];
        template = `<li class="indented-li">
                        <label>
                          <input class="filled-in settings_addon_checkbox" type="checkbox" name="{id}" id="{id}" settings_ignore='true' {checked} />
                          <span>{name} <span class="helper-text">(v{version})</span></span>
                          <br />
                          <span class="helper-text">{description}</span>
                        </label>
                      </li>`;
        template = template
          .replace("{id}", slugToId(addon.slug))
          .replace("{id}", slugToId(addon.slug))
          .replace("{description}", addon.description)
          .replace("{name}", addon.name)
          .replace("{version}", addon.installed)
          .replace("{checked}", exclude_addons.includes(addon.slug) ? "" : "checked");
        $("#settings_addons").append(template);
      }

      $("#settings_error_div").hide();
      M.updateTextFields();
      $("#use_ssl").trigger("change");
      $("#generational_enabled").trigger("change");
      $("#partial_snapshots").trigger("change");
      $("#expose_extra_server").trigger("change");
      settingsChanged = false;
      snapshotNameExample();

      // Configure the visibility/link of the "current snapshot folder" help text and button.
      if (data.snapshot_folder && data.snapshot_folder.length > 0) {
        $("#current_folder_span").show()
        $('#current_folder_link').attr("href", "https://drive.google.com/drive/u/0/folders/" + data.snapshot_folder);
      } else {
        $("#current_folder_span").hide();
      }

      if (config.specify_snapshot_folder && last_data && last_data.drive_enabled) {
        $("#choose_folder_controls").show();
      } else {
        $("#choose_folder_controls").hide();
      }

      $("#settings_specify_folder_id").val(data.snapshot_folder);

      if (config.hasOwnProperty("snapshot_password")) {
        $("#snapshot_password").data("old_password", config.snapshot_password);
      } else {
        $("#snapshot_password").data("old_password", "");
      }
      $("#snapshot_password_reenter").val("");
      updateColorSelector($("#background_color"), Color.parse(config.background_color));
      updateColorSelector($("#accent_color"), Color.parse(config.accent_color));
      checkForSecret();
      M.Modal.getInstance(document.querySelector('#settings_modal')).open();
      showPallette($("#background_color"));
      showPallette($("#accent_color"));
    }, "json")
}

function chooseFolderChanged() {
  if ($("#specify_snapshot_folder").is(':checked') && (config.specify_snapshot_folder || config_data.is_custom_creds) && last_data && last_data.drive_enabled) {
    $("#choose_folder_controls").show();
  } else {
    $("#choose_folder_controls").hide();
  }
}

function saveSettings() {
  if (!document.getElementById('settings_form').checkValidity()) {
    showSettingError({message: "Some configuration is invalid, check for red errors up above."})
    return;
  }

  if (!checkForSecret()) {
    showSettingError({message: "New snapshots passwords don't match"})
    return;
  }
  toast("Saving...")
  var config = {}
  $("select", $("#settings_form")).each(function () {
    var target = $(this)
    config[target.attr("id")] = target.val();
  });
  $("input", $("#settings_form")).each(function () {
    var target = $(this)
    if (target.attr("settings_ignore") == "true") {
      return;
    }
    var value = target.val()
    if (target.attr("type") == "checkbox") {
      value = target.prop('checked')
    } else {
      if (value.length == 0) {
        return;
      } else if (target.attr("type") == "number") {
        value = parseInt(value)
      }
    }
    config[target.attr("id")] = value;
  });
  excluded_addons = ""
  excluded_folders = ""
  if ($("#partial_snapshots").prop('checked')) {
    $(".settings_folder_checkbox").each(function () {
      if (!$(this).is(":checked")) {
        excluded_folders = excluded_folders + idToSlug($(this).attr('id')) + ",";
      }
    });
    $(".settings_addon_checkbox").each(function () {
      if (!$(this).is(":checked")) {
        excluded_addons = excluded_addons + idToSlug($(this).attr('id')) + ",";
      }
    });
  }
  config.exclude_folders = excluded_folders.replace(/(^,)|(,$)/g, "");
  config.exclude_addons = excluded_addons.replace(/(^,)|(,$)/g, "");
  if (!$("#generational_enabled").prop('checked')) {
    generational_delete = ["generational_days", "generational_weeks", "generational_months", "generational_years"] 
    for (prop in generational_delete) {
      if (config.hasOwnProperty(generational_delete[prop])) {
        delete config[generational_delete[prop]];
      }
    }
  }
  config.background_color = $("#background_color").html();
  config.accent_color = $("#accent_color").html();

  modal = M.Modal.getInstance(document.getElementById("settings_modal"))
  postJson("saveconfig", {"config": config, "snapshot_folder": $("#settings_specify_folder_id").val()}, closeSettings, showSettingError); 
}

function closeSettings(){
  M.Modal.getInstance(document.getElementById("settings_modal")).close()
}

function showSettingError(e){
  var element = $("#settings_error");
  element.html(e.message);
  $("#settings_error_div").fadeIn(400);
}
