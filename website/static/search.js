// Mentor search inside the website page. The cards are already in the page,
// placed there as it was served; this only hides the ones that do not match,
// using the chapter applications' search (ruling 33, WT-46).
(function () {
  var root = document.querySelector("[data-cmw-search]");
  if (!root) return;
  var input = root.querySelector(".cmw-search__input");
  var cards = Array.prototype.slice.call(root.querySelectorAll(".cmw-card"));
  var timer;
  input.addEventListener("input", function () {
    clearTimeout(timer);
    timer = setTimeout(function () {
      fetch(root.getAttribute("data-cmw-search") + "?q=" + encodeURIComponent(input.value))
        .then(function (r) { return r.json(); })
        .then(function (res) {
          cards.forEach(function (card) {
            var href = card.querySelector(".cmw-card__link").getAttribute("href");
            var slug = href.split("/").filter(Boolean).pop();
            card.hidden = res.slugs.indexOf(slug) === -1;
          });
        })
        .catch(function () { cards.forEach(function (c) { c.hidden = false; }); });
    }, 200);
  });
})();
