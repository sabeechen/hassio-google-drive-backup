settingsChanged = false;

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

function backupNameExample() {
  $("#backup_example").html(exampleBackupName("Full", $("#backup_name").val()));
}

function backupNameOneOffExample() {
  $("#backup_name_example_one_off").html(exampleBackupName("Full", $("#backup_name_one_off").val()));
}

function checkForSecret() {
  var password = $("#backup_password");
  var password2 = $("#backup_password_reenter");
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

  var exclude_addons = [];
  var stop_addons = []
  if (config.hasOwnProperty('exclude_addons') && config.exclude_addons.length > 0) {
    exclude_addons = config.exclude_addons.split(",");
  }
  if (config.hasOwnProperty('stop_addons') && config.stop_addons.length > 0) {
    stop_addons = config.stop_addons.split(",");
  }

  setInputValue("partial_backups", config.exclude_folders.length > 0 || exclude_addons.length > 0);
  setInputValue("stop_addons", stop_addons.length > 0);

  // Set the state of excluded and stopped addons.
  $("#settings_addons").html("");
  $("#stopped_addons").html("");
  for (addon in addons) {
    addon = addons[addon];
    template = `<li class="indented-li">
                    <label>
                      <input class="filled-in {selector}" type="checkbox" name="{id}" id="{id}" data-slug="{slug}" settings_ignore='true' {checked} />
                      <span>{name} <span class="helper-text">(v{version})</span></span>
                      <br />
                      <span class="helper-text">{description}</span>
                    </label>
                  </li>`;
    template = template
      .replace("{id}", addon.slug)
      .replace("{id}", addon.slug)
      .replace("{slug}", addon.slug)
      .replace("{description}", addon.description)
      .replace("{name}", addon.name)
      .replace("{version}", addon.version);

    $("#settings_addons").append(template.replace("{checked}", exclude_addons.includes(addon.slug) ? "" : "checked").replace("{selector}", "settings_addon_checkbox"));
    $("#stopped_addons").append(template.replace("{checked}", stop_addons.includes(addon.slug) ? "checked" : "").replace("{selector}", "settings_stop_addon_checkbox"));
  }

  $("#folder_selection_list").html("");
  for (folder of data.folders) {
    template = `<li class="indented-li">
                  <label class="checkbox-label">
                    <input class="filled-in settings_folder_checkbox" settings_ignore="true" type="checkbox" name="{id}" id="{id}" data-slug="{slug}" {checked} />
                    <span class="checkbox-label">{name}</span>
                    <br />
                    <span class="helper-text">{description}</span>
                  </label>
                </li>`;
    template = template
      .replace("{id}", folder.id)
      .replace("{id}", folder.id)
      .replace("{slug}", folder.slug)
      .replace("{description}", folder.description)
      .replace("{name}", folder.name)
      .replace("{name}", folder.slug)
      .replace("{checked}",  config.exclude_folders.includes(folder.slug) ? "" : "checked");
    $("#folder_selection_list").append(template);
  }

  $("#settings_error_div").hide();
  M.updateTextFields();
  $("#use_ssl").trigger("change");
  $("#generational_enabled").trigger("change");
  $("#partial_backups").trigger("change");
  $("#expose_extra_server").trigger("change");
  settingsChanged = false;
  backupNameExample();

  // Configure the visibility/link of the "current backup folder" help text and button.
  if (data.backup_folder && data.backup_folder.length > 0) {
    $("#current_folder_span").show()
    $('#current_folder_link').attr("href", "https://drive.google.com/drive/u/0/folders/" + data.backup_folder);
  } else {
    $("#current_folder_span").hide();
  }

  if (config.specify_backup_folder && last_data && last_data.sources.GoogleDrive.enabled) {
    $("#choose_folder_controls").show();
  } else {
    $("#choose_folder_controls").hide();
  }

  setInputValue("settings_specify_folder_id", data.backup_folder);

  if (config.hasOwnProperty("backup_password")) {
    $("#backup_password").data("old_password", config.backup_password);
  } else {
    $("#backup_password").data("old_password", "");
  }
  $("#backup_password_reenter").val("");
  updateColorSelector($("#background_color"), Color.parse(config.background_color));
  updateColorSelector($("#accent_color"), Color.parse(config.accent_color));
  checkForSecret();
  M.Modal.getInstance(document.querySelector('#settings_modal')).open();
  showPallette($("#background_color"));
  showPallette($("#accent_color"));

  toggleSlide(document.querySelector('#stop_addons'), 'settings_stop_addons_details');
  updateIgnoredBackupOptions();
  M.updateTextFields();
}

function chooseFolderChanged() {
  if ($("#specify_backup_folder").is(':checked') && last_data && last_data.sources.GoogleDrive.enabled) {
    $("#choose_folder_controls").show();
  } else {
    $("#choose_folder_controls").hide();
  }
  M.updateTextFields();
}

function updateIgnoredBackupOptions() {
  if ($("#ignore_upgrade_backups").prop('checked') || $("#ignore_other_backups").prop('checked')) {
    $("#ignored-backup-duration-block").fadeIn();
  } else {
    $("#ignored-backup-duration-block").fadeOut();
  }
}

function saveSettings() {
  if (!document.getElementById('settings_form').checkValidity()) {
    showSettingError({message: "Some configuration is invalid, check for red errors up above."})
    return;
  }

  if (!checkForSecret()) {
    showSettingError({message: "New backup passwords don't match"})
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
  if ($("#partial_backups").prop('checked')) {
    $(".settings_folder_checkbox").each(function () {
      if (!$(this).is(":checked")) {
        excluded_folders = excluded_folders + $(this).data("slug") + ",";
      }
    });
    $(".settings_addon_checkbox").each(function () {
      if (!$(this).is(":checked")) {
        excluded_addons = excluded_addons + $(this).data('slug') + ",";
      }
    });
  }
  if ($("#stop_addons").prop('checked')) {
    $(".settings_stop_addon_checkbox").each(function () {
      if ($(this).is(":checked")) {
        stop_addons = stop_addons + $(this).data('slug') + ",";
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
  postJson("saveconfig", {"config": config, "backup_folder": $("#settings_specify_folder_id").val()}, closeSettings, showSettingError); 
}

function closeSettings(){
  M.Modal.getInstance(document.getElementById("settings_modal")).close()
}

function showSettingError(e){
  var element = $("#settings_error");
  element.html(e.message);
  $("#settings_error_div").fadeIn(400);
}
