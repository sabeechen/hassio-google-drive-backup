tooltipBackedUp = "This backup has been uploaded to Google Drive."
tooltipDriveOnly = "This backup is only in Google Drive. Select \"Upload\" from the actions menu to Upload it to Home Assistant."
tooltipHassio = "This backup is only in Home Assistant. Change the number of backups you keep in Drive to get it to upload."
tooltipWaiting = "This backup is waiting to upload to Google Drive."
tooltipLoading = "This backup is being downloaded from Google Drive to Home Assistant.  Soon it will be available to restore."
tooltipPending = "This backup is being created.  If it takes a long time, see the addon's FAQ on GitHub"
tooltipUploading = "This backup is being uploaded to Google Drive."

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
 var name_keys = {}

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

function downloadBackup(target) {
  window.location.assign('download?slug=' + encodeURIComponent($(target).data('backup').slug));
}

function uploadBackup(target) {
  var slug = $(target).data('backup').slug;
  var name = $(target).data('backup').name;
  $("#do_upload_button").attr("onClick", "doUpload('" + slug + "', '" + name + "')");
}

function doUpload(slug, name) {
  message = "Uploading '" + name + "'";
  url = "upload?slug=" + encodeURIComponent(slug);
  postJson(url, {}, refreshstats, null, message);
}

function configureDetailBadge(name, text, show) {
  let container = $('.' + name);
  let span = $('.detail-name', container);
  if (show) {
    span.html(text);
    container.show();
  } else {
    container.hide();
  }
}
 var SIZE_SI = ["B", "kB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB"]
function asSizeString(size) {
  current = size * 1.0;
  for (let id in SIZE_SI) {
      if (current < 1024) {
          return (Math.round(current * 10) / 10) + " " + SIZE_SI[id];
      }
      current /= 1024
  }
  return "Beyond mortal comprehension"
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

function callBackupSnapshot(doSwitch) {
  var url = "callbackupsnapshot?switch=" + doSwitch;
  postJson(url, {}, function (data) {
    $('#backup_upgrade_card').fadeOut(500);
    refreshstats();
  }, null, "Saving...");
}

function ackCheckIgnoredBackups() {
  postJson("ackignorecheck", {}, function (data) {
    $('#ignore_helper_card').fadeOut(500);
  }, null, "Acknowledging...");
  
}

function resolvefolder(use_existing) {
  var url = "resolvefolder?use_existing=" + use_existing;
  postJson(url, {}, refreshstats, null, null);
  setErrorWatermark();
  $('#existing_backup_folder').hide();
  refreshstats();
}

function allowImmediateBackup(use_existing) {
  var url = "ignorestartupcooldown";
  postJson("ignorestartupcooldown", {}, refreshstats, null, "Ignoring delay...");
  $('#backups_boot_waiting_card').hide();
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
      if (data.hasOwnProperty("reload_page") && data.reload_page) {
        // Reload the page
        window.location.assign(getInnerHomeUri());
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
      } 
      button_text = "&nbsp;&nbsp;<a class='btn-flat' target='_blank' onClick=\"$('#error_details_card').fadeIn(400);return false;\">Details</a>"
      $('#error_details_paragraph').text(info.details);

      M.toast({ html: info.message + button_text, displayLength: 10000 });
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
      $("#backups_loading").show();
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

    $(".source_title", template).html("in " + source.title );
    $("use", template).attr('xlink:href', "#" + source.icon);

    if (source.retained > 0) {
      $(".source_retain_count", template).html(source.retained);
      $(".source_retain_label", template).show();
    } else {
      $(".source_retain_label", template).hide();
    }
    if (source.ignored > 0) {
      $(".source_ignored_count", template).html(source.ignored);
      $(".source_ignored_size", template).html(source.ignored_size);
      $(".source_ignored_label", template).show();
    } else {
      $(".source_ignored_label", template).hide();
    }
    $(".source_backup_count", template).html(source.backups + " (" + source.size + ")");

    if (source.hasOwnProperty("free_space")) {
      $('.source_free_space_text', template).html(source.free_space + " remaining");
      $('.source_free_space_tooltip', template).attr("data-tooltip", "An estimate of the space available in " + source.title + ".");
      $('.source_free_space', template).show();
    } else {
      $('.source_free_space', template).hide();
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

function processBackupsUpdate(data) {
  let detail_modal = document.getElementById('details_modal');
  let detail_modal_slug = $("#details_modal").data('slug');
  detail_modal = M.Modal.getInstance(detail_modal);

  let regular_backups = [];
  let ignored_backups = [];
  for (var key in data.backups) {
    if (data.backups.hasOwnProperty(key)) {
      backup = data.backups[key];
      if (backup.ignored) {
        ignored_backups.push(backup);
      } else {
        regular_backups.push(backup);
      }

       // Update the detail modal is necessary
       if (detail_modal_slug == backup.slug && detail_modal && detail_modal.isOpen) {
        setValuesForBackupUpdate(backup);
      }
    }
  }

  let count_regular = populateBackupDiv($('#backups'), regular_backups, "archive");
  let count_ignored = populateBackupDiv($('#backups_ignored'), ignored_backups, "cloud_off");

  if (count_ignored == 0) {
    $(".ignored_backup_slider").addClass("default-hidden");
  } else {
    $(".ignored_backup_slider").removeClass("default-hidden");
  }
  if (count_ignored > 1) {
    $(".ignored_backup_plural").removeClass("default-hidden");
  } else {
    $(".ignored_backup_plural").addClass("default-hidden");
  }

  $(".ignored_backup_count").html(count_ignored);
  return count_regular + count_ignored;
}

function populateBackupDiv(backup_div, backups, icon) {
  slugs = []
  count = 0;
  for (var key in backups) {
    if (backups.hasOwnProperty(key)) {
      count++;
      backup = backups[key];
      // try to find the item
      var template = $(".slug" + backup.slug, backup_div);
      slugs.push(backup.slug);
      var isNew = false;
      if (template.length == 0) {
        var template = $('#backup-template').find(".backup-ui").clone();
        template.addClass("slug" + backup.slug);
        template.addClass("active-backup");
        template.data("slug", backup.slug);
        template.data("timestamp", backup.timestamp);
        $("#backup_card", template).attr('id', "backup_card" + backup.slug);
        $("#loading", template).attr('id', "loading" + backup.slug);
        $(".backup_icon", template).html(icon);
        isNew = true;
      }

      $("#size", template).html(backup['size']);
      if (backup['type'].toLowerCase() == 'full') {
        $("#type", template).html("Full backup");
      } else if (backup['type'].toLowerCase() == 'partial') {
        $("#type", template).html( "Partial backup");
      } else {
        $("#type", template).html('');
      }
      
      $("#createdAt", template).html(backup['createdAt']);
      $("#name", template).html(backup['name']);
      $("#name", template).attr('title', backup['name']);
      $("#status", template).html(backup['status']);
      if (backup.status_detail) {
        $("#gen_detail", template).show();
        tooltip = "Kept generationally for " + backup.status_detail[0];
        $("#gen_detail", template).attr('data-tooltip', tooltip);
      } else {
        $("#gen_detail", template).hide();
      }
      

      if (backup.protected) {
        $(".icon-protected", template).show();
      } else {
        $(".icon-protected", template).hide();
      }

      delete_next = [];
      retained = false;
      for (let source of backup.sources){
        if (source.delete_next) {
          delete_next.push(source);
        }
        if (source.retained) {
          retained = true;
        }
      }
      if (delete_next.length > 1) {
        $(".icon-warn-delete", template).show();
        $(".icon-warn-delete", template).attr("data-tooltip", "This backup will be deleted next from " + delete_next.length + " places when a new backup is created.");
      } else if (delete_next.length == 1) {
        $(".icon-warn-delete", template).show();
        $(".icon-warn-delete", template).attr("data-tooltip", "This backup will be deleted next from " + sourceToName(delete_next[0].key) + " when a new backup is created.");
      } else {
        $(".icon-warn-delete", template).hide();
      }

      if (retained) {
        $(".icon-retain", template).show();
      } else {
        $(".icon-retain", template).hide();
      }

      tip = "Help unavailable";

      if (backup.status.includes("Drive")) {
        tip = tooltipDriveOnly;
      } else if (backup.status.includes("Backed Up")) {
        tip = tooltipBackedUp;
      } else if (backup.status.includes("Loading")) {
        tip = tooltipLoading;
      } else if (backup.status.includes("HA Only")) {
        tip = tooltipHassio;
      } else if (backup.status.includes("Pending")) {
        tip = tooltipPending;
      } else if (backup.status.includes("Upload")) {
        tip = tooltipUploading;
      } else if (backup.status.includes("aiting")) {
        tip = tooltipWaiting;
      }
      $("#status-help", template).attr("data-tooltip", tip);

      if (isNew) {
        before = null;
        // Find where the backup should be inserted, which is almost always at the top.
        // This is an inefficient way of sorting but prevents juggling DOM entities around
        // and the "search" is almsot always O(1) in practice.
        $(".active-backup", backup_div).each(function () {
          if (template.data('timestamp') > $(this).data('timestamp')) {
            before = $(this);
            return false;
          }
        });
        if (before != null) {
          template.insertBefore(before);
        } else {
          backup_div.append(template);
        }
      }

      if (backup.isPending) {
        $("#loading" + backup.slug).show();
        $("#backup_card" + backup.slug).css("cursor", "auto");
      } else {
        $("#loading" + backup.slug).hide();
        $("#backup_card" + backup.slug).css("cursor", "pointer");
      }

      // Set up context
      $("#backup_card" + backup.slug).data('backup', backup);
    }
  }
  // Remove the backup card if the backup was deleted.
  $(".active-backup", backup_div).each(function () {
    var backup = $(this)
    if (!slugs.includes(backup.data('slug'))) {
      backup.remove();
    }
  });
  return count;
}

function processStatusUpdate(data) {
  name_keys = data.backup_name_keys;
  $('#last_backup').empty().append(data.last_backup_text);
  $('#last_backup').attr("datetime", data.last_backup_machine);
  $('#last_backup').attr("title", data.last_backup_detail);

  $('#next_backup').empty().append(data.next_backup_text);
  $('#next_backup').attr("datetime", data.next_backup_machine);
  $('#next_backup').attr("title", data.next_backup_detail);

  if (data.sources.GoogleDrive.enabled && data.folder_id && data.folder_id.length > 0 ) {
    $('.open_drive_link').attr("href", "https://drive.google.com/drive/u/0/folders/" + data.folder_id);
    $('.open_drive_menu').show()
  } else {
    $('.open_drive_menu').hide()
  }

  processSourcesUpdate(data.sources);
  count = processBackupsUpdate(data);

  // Update the "syncing" toast message
  if (data.syncing) {
    if (sync_toast == null) {
      sync_toast = M.toast({ html: '<span>Syncing...</span><a class="btn-flat toast-action" onclick="cancelSync()">Cancel</button>', displayLength: 999999999 })
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
      $("#no_backups_block").show();
      $("#backups_loading").hide();
    } else {
      $("#backups_loading").show();
      $("#no_backups_block").hide();
    }
  } else {
    $("#no_backups_block").hide();
    $("#backups_loading").hide();
  }

  var found = false;
  var error = data.last_error;
  $('.error_card').each(function (i) {
    var item = $(this);
    let id = item.attr('id');
    if (id == "error_card" || id == "error_details_card") {
      // This card gets handled separately because it catches any other error.
      return;
    }
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
    if (!card.is(":visible")) {
      card.fadeIn();
    }
    populateGitHubInfo(card, data.last_error);
  } else {
    $("#error_card").hide();
  }

  // Only show one of the "question" cards at a TimeRanges, ir order to prevent the UI from blowing up
  let question_card = null;
  if (data.notify_check_ignored) {
    question_card = "ignore_helper_card";
  } else if (data.backup_cooldown_active) {
    question_card = "backups_boot_waiting_card";
  } else if(data.warn_ingress_upgrade && !hideIngress) {
    question_card = "ingress_upgrade_card";
  } else if (data.ask_error_reports && !found) {
    question_card = "error_reports_card";
  } else if (data.warn_backup_upgrade && !found) {
    question_card = "backup_upgrade_card";
  }

  $('.question-card').each(function (i) {
    let item = $(this);
    let id = item.attr('id');
    let visible = item.is(":visible");
    if (id == question_card && !visible) {
        item.fadeIn(500);
        item.slideDown(1000);
    } else if (id != question_card && visible) {
        item.slideUp(1000);
        item.fadeOut(500);
    }
  });

  if (data.is_custom_creds) {
    $(".hide-for-custom-creds").hide();
    $(".hide-for-default-creds").show();
  } else {
    $(".hide-for-custom-creds").show();
    $(".hide-for-default-creds").hide();
  }


  $("#restore_hard_link").attr("href", getHomeAssistantUrl(data.restore_backup_path, data.ha_url_base));

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

function newBackupClick() {
  setInputValue("retain_drive_one_off", false);
  setInputValue("retain_ha_one_off", false);
  setInputValue("backup_name_one_off", "");
  backupNameOneOffExample();
  M.Modal.getInstance(document.querySelector('#backupmodal')).open();
}

function doNewBackup() {
  var drive = $("#retain_drive_one_off").prop('checked');
  var ha = $("#retain_ha_one_off").prop('checked');
  var name = $("#backup_name_one_off").val()
  var url = "backup?custom_name=" + encodeURIComponent(name) + "&retain_drive=" + drive + "&retain_ha=" + ha;
  postJson(url, {}, refreshstats, null, "Requesting backup (takes a few seconds)...");
  return false;
}

function allowDeletion(always) {
  var url = "confirmdelete?always=" + always;
  postJson(url, {}, refreshstats, null, "Allowing deletion and syncing...");
}

function chooseBackupFolder() {
  window.open(last_data.choose_folder_url);
}

function skipLowSpaceWarning() {
  postJsonCloseErrorDialog("skipspacecheck", "low_space");
}



$(document).ready(function () {
  if (window.top.location === window.location) {
    // We're in a standard webpage, show the full header
    $(".ingress-only").hide();
    $(".nav-wrapper .right").addClass("hide-on-med-and-down")
  } else {
    // We're in an ingress iframe.
    $(".non-ingress").hide();
    $(".nav-wrapper .brand-logo").addClass("hide-on-med-and-down")
  }
  M.Tabs.init(document.querySelector("#bug_report_tabs"), { "onShow": renderMarkdown });
});


function copyFromInput(id) {
  var copyText = document.getElementById(id);
  copyText.select();
  document.execCommand("copy");
}

function saveFolder(id) {
  url = "changefolder?id=" + id
  postJson(url, {}, refreshstats, null, "Setting backup folder...");
}

function exampleBackupName(backup_type, template) {
  name_keys["{type}"] = $("#partial_backups").is(':checked') ? "Partial" : "Full";
  if (template.length == 0) {
    template = last_data.backup_name_template;
  }
  for (key in name_keys) {
    template = template.replace(key, name_keys[key]);
  }
  return template;
}
