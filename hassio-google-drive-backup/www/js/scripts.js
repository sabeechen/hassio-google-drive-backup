
tooltipBackedUp = "This snapshot has been backed up to Google Drive."
tooltipDriveOnly = "This snapshot is only in Google Drive. Select \"Upload\" from the actions menu to Upload it to Hass.io."
tooltipHassio = "This snapshot is only in Hass.io. Change the number of snapshots you keep in Drive to get it to upload."
tooltipWaiting = "This snapshot is waiting to upload to Google Drive."
tooltipLoading = "This snapshot is being downloaded from Google Drive to Hass.io.  Soon it will be available to restore."
tooltipPending = "This snapshot is being created.  If it takes a long time, see <a href='link/link'>this help.</a>"
tooltipUploading = "This snapshot is being uploaded to Google Drive."

function toggleSlide(checkbox, target) {
  if ($(checkbox).is(':checked')) {
    $('#' + target).slideDown(400);
  } else {
    $('#' + target).slideUp(400);
  }
}

function restoreClick(target) {
  window.top.location.replace($(target).data('url'))
}

function setInputValue(id, value) {
  if (value == null) {
    // Leave at default
    return;
  }
  if (typeof(value) == 'boolean') {
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
  M.toast({ html: "Uploading '" + name + "'", displayLength: 9999999 });
  $.get("upload?slug=" + encodeURIComponent(slug),
    function (data) {
      M.Toast.dismissAll();
      errorToast(data)
      refreshstats();
    }, "json")
    .fail(
      function (e) {
        M.Toast.dismissAll();
        errorToast(e)
      }
    )
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
      $("#details_addons").append("<li>" + addon.name + " <span class='grey-text text-darken-2'>(v" + addon.version + ")</span></li>")
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


function triggerBackup() {
  var jqxhr = $.get("backupnow",
    function (data) {
      refreshstats();
    }, "json")
}

function errorReports(send) {
  var jqxhr = $.get("errorreports?send=" + send)
  $('#error_reports_card').fadeOut(500)
}
hideIngress = false;
function exposeServer(expose) {
  hideIngress = true;
  var jqxhr = $.get("exposeserver?expose=" + expose,
    function (data) {
    }, "json").fail(
      function() {
        // The server is restarting, so we expect the request to fail.
        if (expose == 'false' && last_data && last_data.hasOwnProperty('ingress_url')) {
          setTimeout(function() {
            window.top.location.assign(last_data.ingress_url);
          }, 5000);
        }
      }
    );
  $('#ingress_upgrade_card').fadeOut(500)
}

function triggerSync() {
  toast("Syncing now...")
  var jqxhr = $.get("backupnow",
    function (data) {
      refreshstats();
      toast("Done")
    }, "json")
}

function toast(text) {
  M.toast({ html: text });
}

// Triggers showing a modal confirmation dialog to delete a snapshot
function confirmDeleteSnapshot(target) {
  var snapshot = $(target).data('snapshot');
  var slug = snapshot['slug'];
  var inDrive = snapshot['inDrive'];
  var inHA = snapshot['inHA'];
  $("#delete_drive").attr("onClick", "deleteSnapshot('" + slug + "'," + inDrive + ",false)");
  $("#delete_ha").attr("onClick", "deleteSnapshot('" + slug + "',false," + inHA + ")");
  $("#delete_both").attr("onClick", "deleteSnapshot('" + slug + "'," + inDrive + "," + inHA + ")");
  if (inDrive && inHA) {
    $("#delete_text").text("Are you sure you want to delete this snapshot?  You can delete it in Drive, Home assistant, or both.");
    $("#delete_drive").show();
    $("#delete_ha").show();
    $("#delete_both").show();
  } else if (inDrive && !inHA) {
    $("#delete_text").text("Are you sure you want to delete this snapshot from Google Drive?  It isn't stored in Home Assistant, so it will be gone forever.");
    $("#delete_drive").show();
    $("#delete_ha").hide();
    $("#delete_both").hide();
  } else if (!inDrive && inHA) {
    $("#delete_text").text("Are you sure you want to delete this snapshot?  It isn't backed up, so it will be gone forever.");
    $("#delete_drive").hide();
    $("#delete_ha").show();
    $("#delete_both").hide();
  }
}

function deleteSnapshot(slug, drive, ha) {
  //console.log("Delete: " + slug + " Drive: " + drive + " HA: " + ha)
  message = "Deleting snapshot from ";
  if (drive && ha) {
    message += "Hass.io and Google Drive"
  } else if (drive) {
    message += "Google Drive"
  } else if (ha) {
    message += "Hass.io"
  } else {
    message += "<i>...nowhere?</i>"
  }
  toast(message);
  // Send the delete request
  var deleteRequest = $.get("deleteSnapshot?slug=" + slug + "&drive=" + drive + "&ha=" + ha + "",
    function (data) {
      if (data.hasOwnProperty("error_details")) {
        errorToast(data)
      } else {
        toast(data.message);
      }
      refreshstats();
    }, "json")
    .fail(
      function (e) {
        errorToast(e)
      }
    )
}

function htmlEntities(str) {
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace("'", "&#39;");
}

function errorToast(error) {
  message = "";
  details = "";
  var isError = false;
  if (error.hasOwnProperty("message") && error.hasOwnProperty("error_details")) {
    // Its an error messag form the server
    message = error.message;
    details = error.error_details;
    isError = true;
  } else if (error.hasOwnProperty("status") && error.hasOwnProperty("statusText") && error.hasOwnProperty("responseText")) {
    // Its an HTTP error, so format appropriately
    message = "Got unexpected HTTP error " + error.status + ": " + error.statusText;
    details = error.responseText;
    isError = true;
  } else if (error.hasOwnProperty("error")) {
    message = error.error
    details = JSON.stringify(error, undefined, 2)
    isError = true;
  } else if (error.hasOwnProperty("message")) {
    message = error.message
    //details = JSON.stringify(error, undefined, 2)
    isError = false;
  } else {
    message = "Got an unexpected error"
    details = JSON.stringify(error, undefined, 2)
    isError = true;
  }

  button_text = ""
  if (details.length > 0) {
    button_text = "&nbsp;&nbsp;<a class='waves-effect waves-light btn' target='_blank' onClick=\"$('#error_details_card').fadeIn(400);return false;\">Details</a>"
    $('#error_details_paragraph').text(details);
  }

  console.log(error)
  toast(message + button_text);
  return isError;
}

errorToasted = false;

last_cred_version = -1;
function reloadForNewCreds() {
  var jqxhr = $.get("getstatus", function (data) {
    if (data.hasOwnProperty("cred_version")) {
      if (last_cred_version == -1) {
        last_cred_version = data.cred_version;
      } else if (last_cred_version != data.cred_version) {
        //reload
        window.location.assign(getWindowRootUri())
      } else {
        last_cred_version = data.cred_version;
      }
    }
  })
}

function getWindowRootUri() {
  var loc = window.location;
  path = loc.pathname.replace("\\", "/");
  path = path.replace("/reauthenticate", "/");
  path = path.replace("/reauthenticate/", "/");
  path = path + "/";
  path = path.replace("//", "/");
  return loc.protocol + "//" + loc.hostname + ":" + loc.port + path;
}

last_data = null;
// Refreshes the display with stats from the server.
function refreshstats() {
  var jqxhr = $.get("getstatus", function (data) {
    $('#ha_snapshots').empty().append(data.ha_snapshots);
    $('#drive_snapshots').empty().append(data.drive_snapshots);
    $('#last_snapshot').empty().append(data.last_snapshot);
    $('#next_snapshot').empty().append(data.next_snapshot);
    $('.open_drive_link').attr("href", "https://drive.google.com/drive/u/0/folders/" + data.folder_id);
    snapshot_div = $('#snapshots')
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
          $("#delete_option", template).attr('id', "delete_option" + snapshot.slug);
          $("#restore_option", template).attr('id', "restore_option" + snapshot.slug);
          $("#upload_option", template).attr('id', "upload_option" + snapshot.slug);
          $("#download_option", template).attr('id', "download_option" + snapshot.slug);
          isNew = true;
        }

        $("#size", template).html(snapshot['size']);
        $("#name", template).html(snapshot['name']);
        $("#status", template).html(snapshot['status']);

        template.data("inDrive", snapshot.inDrive);
        template.data("inHa", snapshot.inHA);

        if (snapshot.protected) {
          $(".icon-protected", template).show();
        } else {
          $(".icon-protected", template).hide();
        }

        tip = "Help unavailable";

        if (snapshot.status.includes("Drive")) {
          tip = tooltipDriveOnly;
        } else if (snapshot.status.includes("Backed Up")) {
          tip = tooltipBackedUp;
        } else if (snapshot.status.includes("Loading")) {
          tip = tooltipLoading;
        } else if (snapshot.status.includes("Hass")) {
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
          template.appendTo(snapshot_div);
          var elems = document.querySelectorAll("#action_dropdown_button" + snapshot.slug)
          var instances = M.Dropdown.init(elems, {'constrainWidth': false });
        }

        if (snapshot.inHA || snapshot.inDrive) {
          $("#action_dropdown_button" + snapshot.slug).show();
        } else {
          $("#action_dropdown_button" + snapshot.slug).hide();
        }

        if (snapshot.inHA) {
          $("#upload_option" + snapshot.slug).hide();
          $("#restore_option" + snapshot.slug).show();
        } else {
          $("#upload_option" + snapshot.slug).show();
          $("#restore_option" + snapshot.slug).hide();
        }

        $("#status-details", template).data('snapshot', snapshot)

        // Set up context menu
        $("#delete_link" + snapshot.slug).data('snapshot', snapshot);
        $("#restore_link" + snapshot.slug).data('url', data.restore_link.replace("{host}", window.location.hostname));
        $("#upload_link" + snapshot.slug).data('snapshot', snapshot);
        $("#download_link" + snapshot.slug).data('snapshot', snapshot);
      }
    }

    $(".active-snapshot").each(function () {
      var snapshot = $(this)
      if (!slugs.includes(snapshot.data('slug'))) {
        snapshot.remove();
      }
    });


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

    if (data.last_error == "creds_bad") {
      $('#error_card').hide();
      $('#drive_full_card').hide();
      $('#creds_bad_card').fadeIn(400);
      $('#cant_reach_google').hide();
    } else if (data.last_error == "drive_full") {
      $('#error_card').hide();
      $('#drive_full_card').fadeIn(400);
      $('#creds_bad_card').hide();
      $('#cant_reach_google').hide();
    } else if (data.last_error == "cant_reach_google") {
      $('#error_card').hide();
      $('#drive_full_card').hide();
      $('#creds_bad_card').hide();
      $('#cant_reach_google').fadeIn(400);
    } else if (data.last_error != "") {
      $('#error_paragraph').text(data.last_error);
      desc = "Please add info about your configuration here, along with a brief description of what you were doing and what happened.  Detail is always helpful for investigating an error.  You can enable verbos logging by setting {\"verbose\": true} in your add-on configuration and including that here.  :\n\n" + data.last_error;
      parts = data.last_error.split('\n');
      var title = "Unknown"
      for (var i = parts.length - 1; i >= 0; i--) {
        if (parts[i].trim() != "") {
          title = parts[i].trim();
          break;
        }
      }
      $('#error_github_link').attr("href", "https://github.com/sabeechen/hassio-google-drive-backup/issues/new?labels[]=People%20Management&labels[]=[Type]%20Bug&title=" + encodeURIComponent(title) + "&assignee=sabeechen&body=" + encodeURIComponent(desc));
      $('#error_github_search').attr("href", "https://github.com/sabeechen/hassio-google-drive-backup/issues?q=" + encodeURIComponent("\"" + title.replace("\"", "\\\"") + "\""));
      $('#error_card').fadeIn(400);
      $('#drive_full_card').hide();
      $('#creds_bad_card').hide();
      $('#cant_reach_google').hide();
    } else {
      $('#error_card').hide();
      $('#drive_full_card').hide();
      $('#creds_bad_card').hide();
      $('#cant_reach_google').hide();
    }

    if (data.ask_error_reports) {
      $('#error_reports_card').fadeIn(500);
    } else {
      $('#error_reports_card').hide();
    }

    if (data.warn_ingress_upgrade && !hideIngress) {
      $('#ingress_upgrade_card').fadeIn(500);
    } else {
      $('#ingress_upgrade_card').hide();
    }

    last_data = data;

    $('.tooltipped').tooltip({ "exitDelay": 1000 });
    if (errorToasted) {
      errorToasted = false;
      M.Toast.dismissAll();
    }
  }, "json").fail(
    function (e) {
      console.log("Status update failed: ");
      console.log(e);
      $("#snapshots_loading").show();
      if (!errorToasted) {
        errorToasted = true;  
        M.toast({ html: 'Lost connection to add-on, will keep trying to connect...', displayLength: 9999999 })
      }
    }
  )
}

function simulateError() {
  $.get("simerror?error=This%20is%20a%20fake%20error.%20Select%20'Stop%20Simulated%20Error'%20from%20the%20menu%20to%20stop%20it.",
    function (data) {
      triggerSync()
    })
}

function stopSimulateError() {
  $.get("simerror?error=",
    function (data) {
      triggerSync()
    })
}

function newSnapshotClick() {
    toast("Requesting snapshot (takes a few seconds)...");

    // request the snapshot
    var jqxhr = $.get("triggerbackup",
      function (data) {
        console.log(data);
        if (!data.hasOwnProperty("name")) {
          errorToast(data)
        } else {
          toast("Requested new snapshot '" + data.name + "'");
          refreshstats();
          triggerBackup();
        }
      }, "json")
      .fail(
        function (e) {
          errorToast(e)
        }
      )

    return false;
}

$(document).ready(function () {
  if (window.top.location == window.location) {
    // We're in a standard webpage, onyl show the header
    $(".ingress-only").hide();
  } else {
    // We're in an ingress iframe.
    $(".non-ingress").hide();
  }
});
