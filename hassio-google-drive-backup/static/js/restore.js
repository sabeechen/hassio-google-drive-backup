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
    message = "Restoring '" + name + "'";
    postJson(url, {}, refreshstats, null, message);
    M.Modal.getInstance(document.getElementById("restoremodal")).close();
  }