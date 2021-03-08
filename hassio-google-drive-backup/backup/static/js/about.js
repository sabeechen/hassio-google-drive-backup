var contributorsLoaded = false;
async function fetchContributors() {
  const data = await fetch("https://api.github.com/repos/sabeechen/hassio-google-drive-backup/contributors");
  const contributorsCountToShow = 14;

  if (data.ok) {
    const contributors = await data.json();
    const containerSimple = document.getElementById("contributors-simple");
    const containerExtra = document.getElementById("contributors-extra");
    containerSimple.innerHTML = "";
    containerExtra.innerHTML = "";
    extra_info = {
      'sabeechen': 'Original author.  Did most of this.',
      'ericmatte': 'Redesigned the UI with divine HTML and CSS wizardry.',
      'jhampson-dbre': "Fixed a really nasty timing bug." 
    };
    contributors.slice(0, contributorsCountToShow).forEach((contributor) => {
      if (contributor.login in extra_info) {
        const img = document.createElement("img");
        img.src = contributor.avatar_url;
        img.className = "contributor-img";
        img.title = `@${contributor.login}`;
        img.alt = img.title;

        const a = document.createElement("a");
        a.href = `https://github.com/${contributor.login}`;
        a.target = "_blank";
        a.appendChild(img);

        const name = document.createElement("span");
        name.innerHTML = `@${contributor.login}<br>${contributor.contributions} contributions`;
        name.classList.add('contributor-name');
        name.classList.add('center')
        a.appendChild(name);

        const div = document.createElement("div");
        div.appendChild(a);

        const detail = document.createElement("span");
        detail.innerHTML = extra_info[contributor.login];
        div.append(detail);
        containerExtra.appendChild(div);
        containerExtra.appendChild(document.createElement("br"));
      } else {
        const img = document.createElement("img");
        img.src = contributor.avatar_url;
        img.className = "contributor-img";
        img.title = `@${contributor.login}`;
        img.alt = img.title;

        const a = document.createElement("a");
        a.href = `https://github.com/${contributor.login}`;
        a.target = "_blank";
        a.appendChild(img);
        containerSimple.appendChild(a);
      }
    });

    document.getElementById("contributors-more-link-count").innerHTML = contributors.length - contributorsCountToShow;
    document.getElementById("contributors-count").innerHTML = contributors.length;
    document.getElementById("contributors-count").classList.remove('default-hidden');
    document.getElementById("contributors-loading").classList.add('default-hidden');
  } else {
    document.getElementById("contributors-loading").classList.add('default-hidden');
  }
}

$(document).ready(function () {
  M.Modal.init(document.querySelector("#about_modal"));
});

function openAbout() {
  if (!contributorsLoaded) {
    fetchContributors();
    contributorsLoaded = true;
  }
  M.Modal.getInstance(document.getElementById("about_modal")).open();
}
