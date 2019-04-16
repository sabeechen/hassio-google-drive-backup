
  all_folder_slugs = ['ssl', "addons/local", "homeassistant", "share"];

  function idToSlug(id) {
    if (id == "folder_addons") {
        return "addons/local";
    } else if (id == "folder_homeassistant") {
        return "homeassistant";
    } else if (id == 'folder_share') {
        return "share";
    } else if (id == "folder_ssl"){
        return "ssl";
    } else {
        return id;
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
  

function loadSettings() {
    var jqxhr = $.get("getconfig",
      function (data) {
        console.log(data)
        setInputValue("max_snapshots_in_hassio", data.max_snapshots_in_hassio);
        setInputValue("max_snapshots_in_google_drive", data.max_snapshots_in_google_drive);
        setInputValue("days_between_snapshots", data.days_between_snapshots);
        setInputValue("snapshot_time_of_day", data.snapshot_time_of_day);
        setInputValue("send_error_reports", data.send_error_reports);
        setInputValue("require_login", data.require_login);
        setInputValue("notify_for_stale_snapshots", data.notify_for_stale_snapshots);
        setInputValue("enable_snapshot_stale_sensor", data.enable_snapshot_stale_sensor);
        setInputValue("enable_snapshot_state_sensor", data.enable_snapshot_state_sensor);

        setInputValue("use_ssl", data.use_ssl);
        setInputValue("certfile", data.certfile);
        setInputValue("keyfile", data.keyfile);

        setInputValue("generational_enabled", 
            data.generational_days > 0 || data.generational_weeks > 0 || data.generational_months > 0 || data.generational_years > 0);
        setInputValue("generational_days", data.generational_days);
        setInputValue("generational_weeks", data.generational_weeks);
        setInputValue("generational_months", data.generational_months);
        setInputValue("generational_years", data.generational_years);
        setInputValue("generational_day_of_month", data.generational_day_of_month);
        setInputValue("generational_day_of_year", data.generational_day_of_year);
        setInputValue("generational_day_of_week", data.generational_day_of_week);

        setInputValue("snapshot_password", data.snapshot_password);

        setInputValue("include_homeassistant", !data.exclude_homeassistant);

        // Set the state of excluded folders.
        var excluded_folders = [];
        if (data.hasOwnProperty('exclude_folders') && data.exclude_folders.length > 0) {
          excluded_folders = data.exclude_folders.split(",");
        }
        for (var i = 0 ; i < all_folder_slugs.length; i++) {
          setInputValue(slugToId(all_folder_slugs[i]), !excluded_folders.includes(all_folder_slugs[i]));
        }
  
        var exclude_addons = [];
        if (data.hasOwnProperty('exclude_addons') && data.exclude_addons.length > 0) {
          exclude_addons = data.exclude_addons.split(",");
        }

        setInputValue("partial_snapshots", data.exclude_homeassistant || excluded_folders.length > 0 || exclude_addons.length > 0);
        
        // Set the state of excluded addons.
        $("#settings_addons").html("");
        for (addon in data.addons) {
          addon = data.addons[addon];
          template = `<li class="indented-li">
                        <label>
                          <input class="filled-in settings_addon_checkbox" type="checkbox" name="{id}" id="{id}" {checked} />
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
  
        $("#settings_error").hide();
        M.updateTextFields();
        $("#use_ssl").trigger("change");
        $("#generational_enabled").trigger("change");
        $("#partial_snapshots").trigger("change");
        M.Modal.getInstance(document.querySelector('#settings_modal')).open();
      }, "json")
  }

  function saveSettings() {
    toast("Saving...", displayLength=999999)
    excluded_addons = ""
    $(".settings_addon_checkbox").each(function () {
      if (!$(this).is(":checked")) {
        excluded_addons = excluded_addons + idToSlug($(this).attr('id')) + ","
      }
    });
    excluded_addons = excluded_addons.replace(/(^,)|(,$)/g, "")
  
    excluded_folders = ""
    $(".settings_folder_checkbox").each(function () {
      if (!$(this).is(":checked")) {
        excluded_folders = excluded_folders + idToSlug($(this).attr('id')) + ","
      }
    });
    excluded_folders = excluded_folders.replace(/(^,)|(,$)/g, "")
    if (!document.getElementById('settings_form').checkValidity()) {
      $("#settings_error").show();
      return;
    }
  
    console.log($('#settings_form').serialize());
    formData = $('#settings_form').serialize() + "&exclude_folders=" + encodeURIComponent(excluded_folders) + "&exclude_addons=" + encodeURIComponent(excluded_addons);
    var jqxhr = $.get("saveconfig?" + formData,
      function (data) {
        M.Toast.dismissAll();
        if (!errorToast(data)) {
          M.Modal.getInstance(document.getElementById("settings_modal")).close();
        }
      }, "json")
      .fail(
        function (e) {
          M.Toast.dismissAll();
          errorToast(e)
        }
      )
  }
  