
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

function snapshotNameExample() {
  $("#snapshot_example").html(exampleSnapshotName("Full", $("#snapshot_name").val()));
}

function snapshotNameOneOffExample() {
  $("#snapshot_name_example_one_off").html(exampleSnapshotName("Full", $("#snapshot_name_one_off").val()));
}

function checkForSecret() {
  if ($("#snapshot_password").val().startsWith("!secret ")) {
    $("#snapshot_password").attr('type', 'text')
  } else {
    $("#snapshot_password").attr('type', 'password')
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
      M.Modal.getInstance(document.getElementById("settings_modal")).close();
    }
  } else {
    M.Modal.getInstance(document.getElementById("settings_modal")).close();
  }
}


function loadSettings() {
  var jqxhr = $.get("getconfig",
    function (data) {
      name_keys = data.name_keys;
      config = data.config;
      addons = data.addons;
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

      // Set helper text for additional server info depending on ingress support
      if (config.support_ingress) {
        $("#expose_extra_server_label").html("Expose an additional UI server on port 1627")
        $("#expose_extra_server_help").html("Your version of Home Assistant supports ingress, so you can access the UI securely by clicking \"WEB UI\" form the add-on page.  If you'd also like to expose the UI from a different port with SSL and authentication options of your own choosing, select this box.")
        $("#expose_extra_server").attr("disabled", false);
      } else {
        $("#expose_extra_server").attr("checked", true);
        $("#expose_extra_server").attr("disabled", true);
        $("#expose_extra_server_label").html("UI Server Options");
        $("#expose_extra_server_help").html("Choose the SSL and authentication settings you'd like to use for this interface below.  In a future version of this add-on, this configuration will be optional if your version of Home Assistant supports ingress.");
      }

      $("#settings_error_div").hide();
      M.updateTextFields();
      $("#use_ssl").trigger("change");
      $("#generational_enabled").trigger("change");
      $("#partial_snapshots").trigger("change");
      $("#expose_extra_server").trigger("change");
      settingsChanged = false;
      snapshotNameExample();
      checkForSecret();
      M.Modal.getInstance(document.querySelector('#settings_modal')).open();
    }, "json")
}

function saveSettings() {
  if (!document.getElementById('settings_form').checkValidity()) {
    showSettingError({message: "Some configuration is invalid, check for red errors up above."})
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
  if (config.hasOwnProperty("expose_extra_server")) {
    // TODO: Ingress: Remove for ingress
    delete config["expose_extra_server"];
  }
  modal = M.Modal.getInstance(document.getElementById("settings_modal"))
  postJson("saveconfig", {"config": config}, closeSettings, showSettingError); 
}

function closeSettings(){
  M.Modal.getInstance(document.getElementById("settings_modal")).close()
}

function showSettingError(e){
  var element = $("#settings_error");
  element.html(e.message);
  $("#settings_error_div").fadeIn(400);
}
