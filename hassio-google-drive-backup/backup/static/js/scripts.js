tooltipBackedUp = "This snapshot has been backed up to Google Drive."
tooltipDriveOnly = "This snapshot is only in Google Drive. Select \"Upload\" from the actions menu to Upload it to Home Assistant."
tooltipHassio = "This snapshot is only in Home Assistant. Change the number of snapshots you keep in Drive to get it to upload."
tooltipWaiting = "This snapshot is waiting to upload to Google Drive."
tooltipLoading = "This snapshot is being downloaded from Google Drive to Home Assistant.  Soon it will be available to restore."
tooltipPending = "This snapshot is being created.  If it takes a long time, see the addon's FAQ on GitHub"
tooltipUploading = "This snapshot is being uploaded to Google Drive."

var github_bug_desc = `
Please add some information about your configuration and the problem you ran into here. 
More info really helps speed up debugging, if you don't even read this and help me understand what happened, I probably won't help you.  
Remember that its just one guy back here doing all of this.  
If english isn't your first language, don't sweat it.  Just try to be clear and I'll do the same for you.  Some things you might consider including:
 * What were you doing when the problem happened?
 * A screenshot if its something visual.
 * What configuration options are you using with the add-on?
 * What logs is the add-on printing out?  You can see the detailed logs by clicking "Logs" at the right of the web-UI.
 * Are there any problematic looking logs from the supervisor?  You can get to them from the Home Assistant Interface from "Supervisor" > "System" > "System Log"
 \n\n`;

function toggleSlide(checkbox, target) {
  if ($(checkbox).is(':checked')) {
    $('#' + target).slideDown(400);
  } else {
    $('#' + target).slideUp(400);
  }
}

function toggleLinkSlide(checkbox, target) {
  target = $('#' + target);
  if (target.is(":visible")) {
    target.slideUp(400);
  } else {
    target.slideDown(400);
  }
}

function sourceToName(source) {
  if (source == "GoogleDrive") {
    return "Google Drive";
  } else if (source == "HomeAssistant") {
    return "Home Assistant";
  } else {
    return "Unknown";
  }
}

function restoreClick(target) {
  $('#restore_help_card').fadeIn(500);
  //window.top.location.replace($(target).data('url'))
}

function setInputValue(id, value) {
  if (value == null) {
    // Leave at default
    return;
  }
  if (typeof (value) == 'boolean') {
    $('#' + id).prop('checked', value);
  } else {
    $('#' + id).val(value);
  }
}

function test(target) {
  console.log(target);
}

function downloadSnapshot(target) {
  window.location.assign('download?slug=' + encodeURIComponent($(target).data('snapshot').slug));
}

function uploadSnapshot(target) {
  var slug = $(target).data('snapshot').slug;
  var name = $(target).data('snapshot').name;
  $("#do_upload_button").attr("onClick", "doUpload('" + slug + "', '" + name + "')");
}

function doUpload(slug, name) {
  message = "Uploading '" + name + "'";
  url = "upload?slug=" + encodeURIComponent(slug);
  postJson(url, {}, refreshstats, null, message);
}

function showDetails(target) {
  var snapshot = $(target).data('snapshot');
  var details = snapshot.details;
  console.log(details)
  $("#details_name").html(snapshot.name);
  $("#details_date").html(snapshot.date);
  $("#details_type").html(snapshot.type);
  if (snapshot.protected) {
    $("#details_password").html("yes");
  } else {
    $("#details_password").html("no");
  }
  if (details) {
    $("#details_ha_version").html(details.homeassistant);
    $("#details_folders").html("")
    for (folder in details.folders) {
      folder = details.folders[folder];
      if (folder == "share") {
        folder = "Share";
      } else if (folder == "ssl") {
        folder = "SSL";
      } else if (folder == "addons/local") {
        folder = "Local add-ons";
      } else if (folder == "homeassistant") {
        folder = "Home Assistant Configuration"
      }
      $("#details_folders").append("<li>" + folder + "</li>");
    }

    $("#details_addons").html("")
    for (addon in details.addons) {
      addon = details.addons[addon];
      $("#details_addons").append("<li>" + addon.name + " <span class='grey-text text-darken-2'>(v" + addon.version + ") " + addon.size + "MB</span></li>")
    }
    $("#details_folders_and_addons").show();
    $("#details_upload_reminder").hide();
  } else {
    $("#details_ha_version").html("?");
    $("#details_folders_and_addons").hide();
    $("#details_upload_reminder").show();
  }

  M.Modal.getInstance(document.querySelector('#details_modal')).open();
}

function errorReports(send) {
  var jqxhr = $.get("errorreports?send=" + send)
  $('#error_reports_card').fadeOut(500)
}
hideIngress = false;
function exposeServer(expose) {
  var url = "exposeserver?expose=" + expose;
  postJson(url, {}, function (data) {
    $('#ingress_upgrade_card').fadeOut(500);
    if (expose == "true") {
      refreshstats();
    } else {
      if (data.hasOwnProperty("redirect")) {
        // Reqirect to the url
        window.location.assign(data.redirect.replace("{host}", window.location.hostname))
      }
    }
  }, null, "Saving setting...");
}

function resolvefolder(use_existing) {
  var url = "resolvefolder?use_existing=" + use_existing;
  postJson(url, {}, refreshstats, null, null);
  setErrorWatermark();
  $('#existing_backup_folder').hide();
  refreshstats();
}

function sync(dialog_class) {
  postJsonCloseErrorDialog("startSync", dialog_class);
}

function postJsonCloseErrorDialog(url, dialog_class) {
  postJson(url, {},
    function (data) {
      if (dialog_class) {
        // Hide the error dialog
        $("." + dialog_class).hide();
        setErrorWatermark();
      }
      refreshstats(data);
    }, null)
}

function toast(text) {
  M.toast({ html: text });
}

function htmlEntities(str) {
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace("'", "&#39;");
}

function postJson(path, json, onSuccess, onFail = null, toastWhile = null) {
  var notification = null
  var returned = false
  if (toastWhile) {
    setTimeout(function () {
      if (!returned) {
        notification = M.toast({ html: toastWhile, displayLength: 99999999 });
      }
    }, 1000);
  }
  $.post({
    url: path,
    data: JSON.stringify(json),
    success: function (data) {
      returned = true;
      if (notification != null) {
        notification.dismiss();
      }
      if (data.hasOwnProperty("message")) {
        toast(data.message);
      }
      if (onSuccess) {
        onSuccess(data);
      }
    },
    dataType: "json",
    contentType: 'application/json'
  }).fail(
    function (e) {
      returned = true;
      if (notification != null) {
        notification.dismiss();
      }
      var info = parseErrorInfo(e);
      if (onFail) {
        onFail(info);
      } else {
        button_text = "&nbsp;&nbsp;<a class='waves-effect waves-light btn' target='_blank' onClick=\"$('#error_details_card').fadeIn(400);return false;\">Details</a>"
        $('#error_details_paragraph').text(info.details);

        M.toast({ html: info.message + button_text, displayLength: 10000 });
      }
    }
  )
}


function parseErrorInfo(e) {
  if (e.hasOwnProperty("message") && e.hasOwnProperty("details")) {
    return {
      message: e.message,
      details: e.details
    }
  }

  if (e.hasOwnProperty("responseText")) {
    try {
      return JSON.parse(e.responseText)
    } catch (err) {
      // Try something else
    }
  }

  if (e.hasOwnProperty("status") && e.hasOwnProperty("statusText") && e.hasOwnProperty("responseText")) {
    // Its an HTTP error, so format appropriately
    return {
      message: "Got unexpected HTTP error " + e.status + ": " + e.statusText,
      details: e.responseText
    }
  }
  return {
    message: "Got an unexpected error",
    details: JSON.stringify(error, undefined, 2)
  }
}

function getInnerHomeUri() {
  return normalizeAddonUrl(URI(window.location.href));
}

function getOutterHomeUri() {
  if (parent !== window) {
    return normalizeAddonUrl(URI(parent.location.href), false);
  } else {
    return getInnerHomeUri()
  }
}

function getHomeAssistantUrl(path, alt_host) {
  if (parent !== window) {
    // Probably this is an ingress window
    var start = URI(normalizeAddonUrl(URI(parent.location.href), false));
    return start.pathname(path).toString();
  } else {
    // Probably this is the addon on a custom port
    var host = URI(window.location.href).hostname();
    return URI(alt_host.replace("{host}", host)).pathname(path).toString();
  }
}


function normalizeAddonUrl(uri, add_trailing_slash = true) {
  path = uri.pathname();
  endings = [
    /\/reauthenticate$/g,
    /\/reauthenticate\/$/g,
    /\/index$/g,
    /\/index\/$/g,
    /\/index.html$/g,
    /\/index.html\/$/g
  ]
  for (var i = 0; i < endings.length; i++) {
    path = path.replace(endings[i], "/");
  }
  if (add_trailing_slash) {
    path = path + "/";
  }
  path = path.replace("//", "/");
  return uri.pathname(path).search("").fragment("").hash("").toString();
}

function cancelSync() {
  postJson("cancelSync", {}, refreshstats, null, "Canceling...")
}

function setErrorWatermark() {
  error_minimum = last_data.last_error_count
}

function bugReport() {
  postJson("makeanissue", {}, openBugDialog, null, "Generating Bug Info...")
}

function openBugDialog(resp) {
  $("#bug_markdown_display").val(resp.markdown);
  renderMarkdown();
  tabs = M.Tabs.getInstance(document.querySelector("#bug_report_tabs"));
  M.Modal.getInstance(document.querySelector('#bug_modal')).open();
  tabs.select("bug_markdown");
  tabs.select("bug_preview");
  tabs.updateTabIndicator();
}

function doBugDetailCopy() {
  tabs.select("bug_markdown");
  var copyText = document.getElementById("bug_markdown_display");
  copyText.select();
  document.execCommand("copy");
  M.toast({ html: "Copied! Now go to GitHub" });
}

function renderMarkdown() {
  $("#bug_preview_display").html(window.markdownit().render($("#bug_markdown_display").val()));
}

sync_toast = null;
error_toast = null
last_data = null;
error_minimum = 0
// Refreshes the display with stats from the server.
function refreshstats() {
  var jqxhr = $.get("getstatus", processStatusUpdate, "json").fail(
    function (e) {
      console.log("Status update failed: ");
      console.log(e);
      $("#snapshots_loading").show();
      if (error_toast == null) {
        M.Toast.dismissAll();
        sync_toast = null;
        error_toast = M.toast({ html: 'Lost connection to add-on, will keep trying to connect...', displayLength: 9999999 })
      }
    }
  )
}

function processSourcesUpdate(sources) {
  sources_div = $('#sources');
  for (var key in sources) {
    if (!sources.hasOwnProperty(key)) {
      continue;
    }
    let source = sources[key];
    
    if (!source.enabled) {
      continue;
    }
    let template = $(".source_" + key);
    let isNew = false;
    if (template.length == 0) {
      isNew = true;
      template = $('#source-template').find(".source-ui").clone();
      template.addClass("source_" + key);
      template.addClass("active_source");
      template.data("source", key);
    }

    $(".source_title", template).html("In " + source.title + ":");

    if (source.retained > 0) {
      $(".source_retain_count", template).html(source.retained);
      $(".source_retain_label", template).show();
    } else {
      $(".source_retain_label", template).hide();
    }
    $(".source_snapshot_count", template).html(source.snapshots + " (" + source.size + ")");

    let free_space = $('.source_free_space', template);
    if (source.hasOwnProperty("free_space")) {
      free_space.html(source.free_space + " remaining");
      free_space.attr("data-tooltip", "An estimate of the space available in " + source.title + ".");
      free_space.show();
    } else {
      free_space.hide();
    }

    if (isNew) {
      sources_div.append(template);
    }
  }
  $(".active_source").each(function () {
    let source = $(this);
    let key = source.data('source');
    if (!(sources.hasOwnProperty(source.data('source')) && sources[key].enabled)) {
      source.remove();
    }
  });
}

function processSnapshotsUpdate(data) {
  snapshot_div = $('#snapshots');
  slugs = []
  var count = 0;
  for (var key in data.snapshots) {
    if (data.snapshots.hasOwnProperty(key)) {
      count++;
      snapshot = data.snapshots[key];
      slugs.push(snapshot.slug);
      // try to find the item
      var template = $(".slug" + snapshot.slug)
      var isNew = false;
      if (template.length == 0) {
        var template = $('#snapshot-template').find(".snapshot-ui").clone();
        template.addClass("slug" + snapshot.slug);
        template.addClass("active-snapshot");
        template.data("slug", snapshot.slug);
        var dropdown = $("#action_dropdown", template);
        dropdown.attr("id", "action_dropdown" + snapshot.slug);
        $("#action_dropdown_button", template).attr("data-target", "action_dropdown" + snapshot.slug);
        $("#action_dropdown_button", template).attr('id', "action_dropdown_button" + snapshot.slug);

        $("#delete_link", template).attr('id', "delete_link" + snapshot.slug);
        $("#restore_link", template).attr('id', "restore_link" + snapshot.slug);
        $("#upload_link", template).attr('id', "upload_link" + snapshot.slug);
        $("#download_link", template).attr('id', "download_link" + snapshot.slug);
        $("#retain_link", template).attr('id', "retain_link" + snapshot.slug);
        $("#delete_option", template).attr('id', "delete_option" + snapshot.slug);
        $("#restore_option", template).attr('id', "restore_option" + snapshot.slug);
        $("#upload_option", template).attr('id', "upload_option" + snapshot.slug);
        $("#download_option", template).attr('id', "download_option" + snapshot.slug);
        $("#retain_option", template).attr('id', "retain_option" + snapshot.slug);
        isNew = true;
      }

      $("#size", template).html(snapshot['size']);
      $("#name", template).html(snapshot['name']);
      $("#status", template).html(snapshot['status']);

      if (snapshot.protected) {
        $(".icon-protected", template).show();
      } else {
        $(".icon-protected", template).hide();
      }

      delete_next = [];
      retained = false;
      for (let source of snapshot.sources){
        if (source.delete_next) {
          delete_next.push(source);
        }
        if (source.retained) {
          retained = true;
        }
      }
      if (delete_next.length > 1) {
        $(".icon-warn-delete", template).show();
        $(".icon-warn-delete", template).attr("data-tooltip", "This snapshot will be deleted next from " + delete_next.length + " places when a new snapshot is created.");
      } else if (delete_next.length == 1) {
        $(".icon-warn-delete", template).show();
        $(".icon-warn-delete", template).attr("data-tooltip", "This snapshot will be deleted next from " + sourceToName(delete_next[0].key) + " when a new snapshot is created.");
      } else {
        $(".icon-warn-delete", template).hide();
      }

      if (retained) {
        $(".icon-retain", template).show();
      } else {
        $(".icon-retain", template).hide();
      }

      tip = "Help unavailable";

      if (snapshot.status.includes("Drive")) {
        tip = tooltipDriveOnly;
      } else if (snapshot.status.includes("Backed Up")) {
        tip = tooltipBackedUp;
      } else if (snapshot.status.includes("Loading")) {
        tip = tooltipLoading;
      } else if (snapshot.status.includes("HA Only")) {
        tip = tooltipHassio;
      } else if (snapshot.status.includes("Pending")) {
        tip = tooltipPending;
      } else if (snapshot.status.includes("Upload")) {
        tip = tooltipUploading;
      } else if (snapshot.status.includes("aiting")) {
        tip = tooltipWaiting;
      }
      $("#status-help", template).attr("data-tooltip", tip);

      if (isNew) {
        snapshot_div.prepend(template);
        var elems = document.querySelectorAll("#action_dropdown_button" + snapshot.slug)
        var instances = M.Dropdown.init(elems, { 'constrainWidth': false });
      }

      if (snapshot.isPending) {
        $("#action_dropdown_button" + snapshot.slug).hide();
      } else {
        $("#action_dropdown_button" + snapshot.slug).show();
      }

      if (snapshot.restorable) {
        $("#restore_option" + snapshot.slug).show();
      } else {
        $("#restore_option" + snapshot.slug).hide();
      }

      if (snapshot.uploadable) {
        $("#upload_option" + snapshot.slug).show();
      } else {
        $("#upload_option" + snapshot.slug).hide();
      }

      $("#status-details", template).data('snapshot', snapshot)

      // Set up context menu
      $("#delete_link" + snapshot.slug).data('snapshot', snapshot);
      //$("#restore_link" + snapshot.slug).data('url', data.restore_link.replace("{host}", window.location.hostname));
      $("#upload_link" + snapshot.slug).data('snapshot', snapshot);
      $("#download_link" + snapshot.slug).data('snapshot', snapshot);
      $("#retain_link" + snapshot.slug).data('snapshot', snapshot);
    }
  }

  $(".active-snapshot").each(function () {
    var snapshot = $(this)
    if (!slugs.includes(snapshot.data('slug'))) {
      snapshot.remove();
    }
  });
  return count;
}

function processStatusUpdate(data) {
  $('#last_snapshot').empty().append(data.last_snapshot_text);
  $('#last_snapshot').attr("datetime", data.last_snapshot_machine);
  $('#last_snapshot').attr("title", data.last_snapshot_detail);

  $('#next_snapshot').empty().append(data.next_snapshot_text);
  $('#next_snapshot').attr("datetime", data.next_snapshot_machine);
  $('#next_snapshot').attr("title", data.next_snapshot_detail);

  if (data.sources.GoogleDrive.enabled && data.folder_id && data.folder_id.length > 0 ) {
    $('.open_drive_link').attr("href", "https://drive.google.com/drive/u/0/folders/" + data.folder_id);
    $('.open_drive_menu').show()
  } else {
    $('.open_drive_menu').hide()
  }

  processSourcesUpdate(data.sources);
  count = processSnapshotsUpdate(data);

  // Update the "syncing" toast message
  if (data.syncing) {
    if (sync_toast == null) {
      sync_toast = M.toast({ html: '<span>Syncing...</span><button class="btn-flat toast-action" onclick="cancelSync()">Cancel</button>', displayLength: 999999999 })
    }
  } else {
    // Make sure the toast isn't up
    if (sync_toast != null) {
      sync_toast.dismiss();
      sync_toast = null
    }
  }


  if (count == 0) {
    if (!data.firstSync) {
      $("#no_snapshots_block").show();
      $("#snapshots_loading").hide();
    } else {
      $("#snapshots_loading").show();
      $("#no_snapshots_block").hide();
    }
  } else {
    $("#no_snapshots_block").hide();
    $("#snapshots_loading").hide();
  }

  var found = false;
  var error = data.last_error;
  $('.error_card').each(function (i) {
    var item = $(this);
    if (data.last_error == null) {
      if (item.is(":visible")) {
        item.hide();
      }
    } else if (item.hasClass(error.error_type) && data.last_error_count != error_minimum && !data.ignore_errors_for_now && !data.ignore_sync_error) {
      found = true;
      if (data.hasOwnProperty('dns_info')) {
        var dns_div = $('.dns_info', item)
        if (dns_div.length > 0) {
          populateDnsInfo(dns_div, data.dns_info)
        }
      }
      if (error.data != null) {
        for (key in error.data) {
          if (!error.data.hasOwnProperty(key)) {
            continue;
          }
          var value = error.data[key];
          var index = key.lastIndexOf("#");
          if (index > 0) {
            var attr = key.slice(index + 1);
            key = key.slice(0, index);
            $("#data_" + key, item).attr(attr, value);
          } else {
            $("#data_" + key, item).html(value);
          }
        }
      }
      if (item.is(":hidden")) {
        item.show()
      }
    } else {
      item.hide();
    }
  });

  if (data.last_error != null && !found && data.last_error_count != error_minimum && !data.ignore_errors_for_now && !data.ignore_sync_error) {
    var card = $("#error_card")
    populateGitHubInfo(card, data.last_error);
    card.fadeIn();
  } else {
    $("#error_card").hide();
  }

  if (data.ask_error_reports && !found) {
    $('#error_reports_card').fadeIn(500);
  } else {
    $('#error_reports_card').hide();
  }

  if (data.is_custom_creds) {
    $(".hide-for-custom-creds").hide();
    $(".hide-for-default-creds").show();
  } else {
    $(".hide-for-custom-creds").show();
    $(".hide-for-default-creds").hide();
  }

  if (data.warn_ingress_upgrade && !hideIngress) {
    $('#ingress_upgrade_card').fadeIn(500);
  } else {
    $('#ingress_upgrade_card').hide();
  }


  $("#restore_hard_link").attr("href", getHomeAssistantUrl(data.restore_snapshot_path, data.ha_url_base));

  last_data = data;

  $('.tooltipped').tooltip({ "exitDelay": 1000 });
  if (error_toast != null) {
    error_toast.dismiss();
    error_toast = null;
  }
}

function populateDnsInfo(target, data) {
  if (data == null) {
    target.html("No DNS info is available")
  } else if (data.hasOwnProperty('error')) {
    target.html(JSON.stringify(data.error))
  } else {
    var html = "";
    for (var host in data) {
      if (data.hasOwnProperty(host)) {
        html += "<div class='col s12 m6 row'> <h6>Host: " + host + "</h6>";
        var ips = data[host];
        for (var ip in ips) {
          if (ips.hasOwnProperty(ip)) {
            result = ips[ip];
            html += "<div class='col s7'>" + ip + "</div><div class='col s5'>" + result + "</div>";
          }
        }
        html += "</div>";
      }
    }
    target.html(html);
  }
}

function populateGitHubInfo(target, error) {
  $('#generic_error_title', target).text(error.message);
  $('#generic_error_details', target).text(error.details);
  $('#error_github_search', target).attr("href", "https://github.com/sabeechen/hassio-google-drive-backup/issues?q=" + encodeURIComponent("\"" + error.message.replace("\"", "\\\"") + "\""));
}

function simulateError() {
  $.get("simerror?error=This%20is%20a%20fake%20error.%20Select%20'Stop%20Simulated%20Error'%20from%20the%20menu%20to%20stop%20it.",
    function (data) {
      sync()
    })
}

function stopSimulateError() {
  $.get("simerror?error=",
    function (data) {
      sync()
    })
}

function newSnapshotClick() {
  setInputValue("retain_drive_one_off", false);
  setInputValue("retain_ha_one_off", false);
  setInputValue("snapshot_name_one_off", "");
  snapshotNameOneOffExample();
  M.Modal.getInstance(document.querySelector('#snapshotmodal')).open();
}

function doNewSnapshot() {
  var drive = $("#retain_drive_one_off").prop('checked');
  var ha = $("#retain_ha_one_off").prop('checked');
  var name = $("#snapshot_name_one_off").val()
  var url = "snapshot?custom_name=" + encodeURIComponent(name) + "&retain_drive=" + drive + "&retain_ha=" + ha;
  postJson(url, {}, refreshstats, null, "Requesting snapshot (takes a few seconds)...");
  return false;
}


function allowDeletion(always) {
  var url = "confirmdelete?always=" + always;
  postJson(url, {}, refreshstats, null, "Allowing deletion and syncing...");
}

function chooseSnapshotFolder() {
  window.open(last_data.choose_folder_url);
}

function skipLowSpaceWarning() {
  postJsonCloseErrorDialog("skipspacecheck", "low_space");
}



$(document).ready(function () {
  if (window.top.location == window.location) {
    // We're in a standard webpage, only show the header
    $(".ingress-only").hide();
  } else {
    // We're in an ingress iframe.
    $(".non-ingress").hide();
  }
  var instance = M.Tabs.init(document.querySelector("#bug_report_tabs"), { "onShow": renderMarkdown });
});


function copyFromInput(id) {
  var copyText = document.getElementById(id);
  copyText.select();
  document.execCommand("copy");
}

function saveFolder(id) {
  url = "changefolder?id=" + id
  postJson(url, {}, refreshstats, null, "Setting snapshot folder...");
}