let contributorsLoaded = false;

const CONTRIBUTORS_API_URL = "https://api.github.com/repos/sabeechen/hassio-google-drive-backup/contributors";
const CONTRIBUTOR_COMMIT_URL = "https://github.com/sabeechen/hassio-google-drive-backup/commits?author={AUTHOR}";
const CONTRIBUTORS_COUNT_TO_SHOW = 14;

const EXTRA_CONTRIBUTORS = {
  "sabeechen": "Original author. Did most of this.",
  "ericmatte": "Redesigned the UI with divine HTML and CSS wizardry.",
  "jhampson-dbre": "Fixed a really nasty timing bug.",
};

function createElementFromHTML(htmlString) {
  var div = document.createElement("div");
  div.innerHTML = htmlString.trim();
  return div.firstChild;
}

function showElement(id) {
  document.getElementById(id).classList.remove("default-hidden");
}

function hideElement(id) {
  document.getElementById(id).classList.add("default-hidden");
}

async function preloadImage(url) {
  return new Promise((resolve) => {
    const img = new Image();
    img.src = url;
    img.onload = () => resolve(img);
  });
}

const extraContributorTemplate = `
<div class="contributor-extra">
  <div class="contributor-img-wrapper"></div>
  <div>
    <div>
      <a href="{hrefUsername}" target="_blank">{username}</a>
      -
      <a href="{hrefContributions}" target="_blank">{contributions}</a>
    </div>
    <div>{details}</div>
  </div>
</div>
`;

async function loadContributor(contributor) {
  const img = await preloadImage(contributor.avatar_url);
  img.className = "contributor-img";
  img.title = `@${contributor.login}`;
  img.alt = img.title;

  const a = document.createElement("a");
  a.href = contributor.html_url;
  a.target = "_blank";
  a.appendChild(img);

  if (contributor.login in EXTRA_CONTRIBUTORS) {
    const div = createElementFromHTML(
      extraContributorTemplate
        .replace("{hrefUsername}", contributor.html_url)
        .replace("{username}", `@${contributor.login}`)
        .replace("{hrefContributions}", CONTRIBUTOR_COMMIT_URL.replace("{AUTHOR}", contributor.login))
        .replace("{contributions}", `${contributor.contributions} contributions`)
        .replace("{details}", EXTRA_CONTRIBUTORS[contributor.login]),
    );
    div.querySelector(".contributor-img-wrapper").appendChild(a);

    return { element: div, isExtra: true };
  } else {
    return { element: a, isExtra: false };
  }
}

async function fetchContributors() {
  if (contributorsLoaded) return;
  
  const data = await fetch(CONTRIBUTORS_API_URL);
  showElement("contributors-loading");
  hideElement("contributors-count");
  hideElement("contributors");

  if (data.ok) {
    const contributors = await data.json();
    const containerSimple = document.getElementById("contributors-simple");
    const containerExtra = document.getElementById("contributors-extra");
    containerSimple.innerHTML = "";
    containerExtra.innerHTML = "";

    const contributorsToShow = contributors.slice(0, CONTRIBUTORS_COUNT_TO_SHOW);
    const contributorItems = await Promise.all(contributorsToShow.map((contributor) => loadContributor(contributor)));

    contributorItems.forEach((item) => {
      (item.isExtra ? containerExtra : containerSimple).appendChild(item.element);
    });

    document.getElementById("contributors-more-link-count").innerText = contributors.length - CONTRIBUTORS_COUNT_TO_SHOW;
    document.getElementById("contributors-count").innerText = contributors.length;
    showElement("contributors-count");
    showElement("contributors");
    contributorsLoaded = true;
  }

  hideElement("contributors-loading");
}

$(document).ready(function () {
  M.Modal.init(document.querySelector("#about_modal"), {
    onOpenStart: () => fetchContributors(),
  });
});
