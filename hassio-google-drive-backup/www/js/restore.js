function restoreSnapshot(target) {
    var data = $(target).data('snapshot').details;
    var slug = data.slug;
    var name = data.name;
    var protected = $(target).data('snapshot').protected;
    if (protected) {
      $("#restore_password_div").show();
    } else {
      $("#restore_password_div").hide();
    }
    $("#do_restore_button").attr("onClick", "doRestore('" + slug + "', '" + name + "', " + protected + ")");
    $("#restore_homeassistant_version").html("(" + data.homeassistant + ")")
     // Set the state of excluded addons.
     $("#restore_addons").html("");
     for (addon in data.addons) {
       addon = data.addons[addon];
       template = `<li class="indented-li">
                     <label>
                       <input class="restore_addon_checkbox" type="checkbox" name="{id}" id="{id}" class="filled-in" checked />
                       <span>{name} <span class="helper-text">(v{version})</span></span>
                       <br />
                     </label>
                   </li>`;
       template = template
         .replace("{id}", slugToId(addon.slug))
         .replace("{id}", slugToId(addon.slug))
         .replace("{name}", addon.name)
         .replace("{version}", addon.version);
       $("#restore_addons").append(template);
     }
  }
  
  function doRestore(slug, name, protected) {
    var password = ""
    if (protected) {
      password = $("#restore_password").val();
      if (password.length == 0) {
        return;
      }
    }
    toast("Restoring '" + name + "'");
    url = "restore?slug=" + encodeURIComponent(slug);
    if (password.length > 0) {
      url = url + "&password=" + encodeURIComponent(password)
    }
    $.get(url,
      function (data) {
        errorToast(data)
        refreshstats();
      }, "json")
      .fail(
        function (e) {
          if (e.hasOwnProperty("readyState")
            && e.hasOwnProperty("status")
            && e.hasOwnProperty("statusText")
            && e.readyState == 0
            && e.status == 0
            && e.statusText == "error") {
            // For some reason, this is what jquery responds with when the server
            // shuts down because of a snapshot so, just continue.
            toast("Resotre has started.  Please wait a while for Home Assistant to come back online.");
            return;
          }
          errorToast(e)
        }
      )
    M.Modal.getInstance(document.getElementById("restoremodal")).close();
  }