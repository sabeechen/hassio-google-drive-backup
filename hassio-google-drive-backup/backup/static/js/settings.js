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
  window.setColors(background, accent);
}

function revertColors() {
  background = Color.parse(defaults.background_color);
  updateColorSelector($("#background_color"), background);
  accent = Color.parse(defaults.accent_color);
  updateColorSelector($("#accent_color"), accent);

  window.setColors(background, accent);
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
      window.setColors(background, accent);
      M.Modal.getInstance(document.getElementById("settings_modal")).close();
    }
  } else {
    background = Color.parse(config.background_color);
    accent = Color.parse(config.accent_color);
    window.setColors(background, accent);
    M.Modal.getInstance(document.getElementById("settings_modal")).close();
  }
}


function loadSettings() {
  postJson("getconfig", {}, handleSettingsDialog, null, "Loading settings...")
}

function handleSettingsDialog(data) {
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
  var stop_addons = []
  if (config.hasOwnProperty('exclude_addons') && config.exclude_addons.length > 0) {
    exclude_addons = config.exclude_addons.split(",");
  }
  if (config.hasOwnProperty('stop_addons') && config.stop_addons.length > 0) {
    stop_addons = config.stop_addons.split(",");
  }

  setInputValue("partial_snapshots", excluded_folders.length > 0 || exclude_addons.length > 0);
  setInputValue("stop_addons", stop_addons.length > 0);

  // Set the state of excluded and stopped addons.
  $("#settings_addons").html("");
  $("#stopped_addons").html("");
  for (addon in addons) {
    addon = addons[addon];
    template = `<li class="indented-li">
                    <label>
                      <input class="filled-in {selector}" type="checkbox" name="{id}" id="{id}" settings_ignore='true' {checked} />
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
      .replace("{version}", addon.installed);

    $("#settings_addons").append(template.replace("{checked}", exclude_addons.includes(addon.slug) ? "" : "checked").replace("{selector}", "settings_addon_checkbox"));
    $("#stopped_addons").append(template.replace("{checked}", stop_addons.includes(addon.slug) ? "checked" : "").replace("{selector}", "settings_stop_addon_checkbox"));
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

  setInputValue("settings_specify_folder_id", data.snapshot_folder);

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
  stop_addons = ""
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
  if ($("#stop_addons").prop('checked')) {
    $(".settings_stop_addon_checkbox").each(function () {
      if ($(this).is(":checked")) {
        stop_addons = stop_addons + idToSlug($(this).attr('id')) + ",";
      }
    });
  }
  config.exclude_folders = excluded_folders.replace(/(^,)|(,$)/g, "");
  config.exclude_addons = excluded_addons.replace(/(^,)|(,$)/g, "");
  config.stop_addons = stop_addons.replace(/(^,)|(,$)/g, "");
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
