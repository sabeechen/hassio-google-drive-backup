async function fetchContributors() {
  const data = await fetch("https://api.github.com/repos/sabeechen/hassio-google-drive-backup/contributors");
  const contributorsCountToShow = 11;

  const contributors = await data.json();
  const container = document.getElementById("contributors");
  container.innerHTML = "";

  contributors.slice(0, contributorsCountToShow).forEach((contributor) => {
    const img = document.createElement("img");
    img.src = contributor.avatar_url;
    img.className = "contributor-img";
    img.title = `@${contributor.login}`;
    img.alt = img.title;

    const a = document.createElement("a");
    a.href = contributor.avatar_url;
    a.appendChild(img);
    container.appendChild(a);
  });

  document.getElementById("contributors-more-link-count").innerHTML = contributors.length - contributorsCountToShow;
  document.getElementById("contributors-count").innerHTML = contributors.length;
}

$(document).ready(function () {
  fetchContributors();
  M.Modal.init(document.querySelector("#about_modal"));
});
